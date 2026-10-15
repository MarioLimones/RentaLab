from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from conftest import authenticate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, ExecutionContext

from rentalab.config import Settings
from rentalab.main import create_app


def test_two_connections_cannot_confirm_incompatible_reservations(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    equipment_payload: dict[str, object],
) -> None:
    """Force the second connection to attempt a write while the first owns the lock."""
    equipment = client.post("/api/equipment", json=equipment_payload).json()
    payload = {
        "equipment_id": equipment["id"],
        "customer_name": "Cliente de concurrencia ficticio",
        "customer_email": "concurrency@example.test",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
    }
    second_app = create_app(settings)
    first_has_lock = Event()
    second_attempted_write = Event()
    first_connections: set[int] = set()
    second_connections: set[int] = set()

    def observe_first_connection(connection: object, _record: object, _proxy: object) -> None:
        first_connections.add(id(connection))

    def observe_second_connection(connection: object, _record: object, _proxy: object) -> None:
        second_connections.add(id(connection))

    def hold_first_write_lock(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: ExecutionContext,
        _executemany: bool,
    ) -> None:
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            first_has_lock.set()
            assert second_attempted_write.wait(timeout=5), "The second writer never attempted SQL"

    def observe_second_write_attempt(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: ExecutionContext,
        _executemany: bool,
    ) -> None:
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            second_attempted_write.set()

    second_client = TestClient(second_app)
    authenticate(second_client)
    event.listen(app.state.engine, "checkout", observe_first_connection)
    event.listen(second_app.state.engine, "checkout", observe_second_connection)
    event.listen(app.state.engine, "after_cursor_execute", hold_first_write_lock)
    event.listen(second_app.state.engine, "before_cursor_execute", observe_second_write_attempt)
    try:
        with second_client, ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(client.post, "/api/reservations", json=payload)
            assert first_has_lock.wait(timeout=5), "Creation did not acquire a SQLite write lock"
            second = executor.submit(second_client.post, "/api/reservations", json=payload)
            responses = [first.result(timeout=10), second.result(timeout=10)]
        assert sorted(response.status_code for response in responses) == [201, 409]
        conflict = next(response for response in responses if response.status_code == 409)
        assert "retry-after" not in conflict.headers
        assert "reserva confirmada" in conflict.json()["detail"]
        assert first_connections and second_connections
        assert first_connections.isdisjoint(second_connections)
        with app.state.engine.connect() as connection:
            confirmed = connection.scalar(
                text("SELECT COUNT(*) FROM reservations WHERE status = 'confirmed'")
            )
        assert confirmed == 1
        reservations = client.get("/api/reservations").json()
        assert len(reservations) == 1
        assert reservations[0]["status"] == "confirmed"
    finally:
        event.remove(app.state.engine, "checkout", observe_first_connection)
        event.remove(second_app.state.engine, "checkout", observe_second_connection)
        event.remove(app.state.engine, "after_cursor_execute", hold_first_write_lock)
        event.remove(second_app.state.engine, "before_cursor_execute", observe_second_write_attempt)
        second_app.state.engine.dispose()


@pytest.mark.parametrize("operation", ["create", "cancel"])
def test_sqlite_busy_is_controlled_and_the_request_can_be_retried_after_unlocking(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    equipment_payload: dict[str, object],
    operation: str,
) -> None:
    equipment = client.post("/api/equipment", json=equipment_payload).json()
    payload = {
        "equipment_id": equipment["id"],
        "customer_name": "Cliente ficticio",
        "customer_email": "busy@example.test",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
    }
    original: dict[str, object] | None = None
    if operation == "cancel":
        created = client.post("/api/reservations", json=payload)
        assert created.status_code == 201
        original = created.json()
        url = f"/api/reservations/{original['id']}/cancel"
        request_json = None
    else:
        url = "/api/reservations"
        request_json = payload

    second_app = create_app(settings.model_copy(update={"sqlite_busy_timeout_ms": 25}))
    try:
        with TestClient(second_app) as second_client:
            authenticate(second_client)
            with app.state.engine.connect() as lock_owner:
                lock_owner.exec_driver_sql("BEGIN IMMEDIATE")
                response = second_client.post(url, json=request_json)
                assert response.status_code == 503
                assert response.headers["retry-after"] == "1"
                assert isinstance(response.json()["detail"], str)
                assert client.get("/api/reservations").json() == (
                    [original] if original is not None else []
                )
                lock_owner.rollback()

            retried = second_client.post(url, json=request_json)
            assert retried.status_code == (201 if operation == "create" else 200)
            assert retried.json()["status"] == (
                "confirmed" if operation == "create" else "cancelled"
            )
            assert len(client.get("/api/reservations").json()) == 1
    finally:
        second_app.state.engine.dispose()


def test_a_commit_blocked_by_a_reader_rolls_back_without_creating_a_reservation(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    equipment_payload: dict[str, object],
) -> None:
    equipment = client.post("/api/equipment", json=equipment_payload).json()
    payload = {
        "equipment_id": equipment["id"],
        "customer_name": "Cliente ficticio",
        "customer_email": "reader@example.test",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
    }
    second_app = create_app(settings.model_copy(update={"sqlite_busy_timeout_ms": 25}))
    try:
        with TestClient(second_app) as second_client:
            authenticate(second_client)
            with app.state.engine.connect() as reader:
                reader.exec_driver_sql("BEGIN")
                reader.exec_driver_sql("SELECT id FROM equipment").all()
                blocked = second_client.post("/api/reservations", json=payload)
                assert blocked.status_code == 503
                assert blocked.headers["retry-after"] == "1"
                assert client.get("/api/reservations").json() == []
                reader.rollback()
            retried = second_client.post("/api/reservations", json=payload)
            assert retried.status_code == 201
            assert len(client.get("/api/reservations").json()) == 1
    finally:
        second_app.state.engine.dispose()
