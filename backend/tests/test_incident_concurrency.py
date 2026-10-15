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


@pytest.mark.parametrize("incident_first", [True, False])
def test_incident_and_booking_use_the_same_sqlite_write_serialization(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    equipment_payload: dict[str, object],
    incident_first: bool,
) -> None:
    """Both write orders have an observable, consistent result across real connections."""
    equipment = client.post("/api/equipment", json=equipment_payload).json()
    incident_payload = {
        "equipment_id": equipment["id"],
        "title": "Incidencia bloqueante ficticia",
        "blocking": True,
    }
    booking_payload = {
        "equipment_id": equipment["id"],
        "customer_name": "Cliente ficticio",
        "customer_email": "concurrency@example.test",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
    }
    first_url = "/api/incidents" if incident_first else "/api/reservations"
    second_url = "/api/reservations" if incident_first else "/api/incidents"
    first_payload = incident_payload if incident_first else booking_payload
    second_payload = booking_payload if incident_first else incident_payload
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
            assert second_attempted_write.wait(timeout=5), "The other writer never attempted SQL"

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
            first = executor.submit(client.post, first_url, json=first_payload)
            assert first_has_lock.wait(timeout=5), "The first writer did not acquire its lock"
            second = executor.submit(second_client.post, second_url, json=second_payload)
            first_response = first.result(timeout=10)
            second_response = second.result(timeout=10)
        assert first_response.status_code == 201
        assert first_connections and second_connections
        assert first_connections.isdisjoint(second_connections)
        with app.state.engine.connect() as connection:
            incident_count = connection.scalar(text("SELECT COUNT(*) FROM incidents"))
            booking_count = connection.scalar(text("SELECT COUNT(*) FROM reservations"))
        assert incident_count == 1
        if incident_first:
            assert second_response.status_code == 409
            assert "retry-after" not in second_response.headers
            assert booking_count == 0
            assert client.get("/api/reservations").json() == []
        else:
            assert second_response.status_code == 201
            assert booking_count == 1
            assert second_response.json()["confirmed_reservation_ids"] == [
                first_response.json()["id"]
            ]
            assert isinstance(second_response.json()["warning"], str)
            assert client.get("/api/reservations").json() == [first_response.json()]
    finally:
        event.remove(app.state.engine, "checkout", observe_first_connection)
        event.remove(second_app.state.engine, "checkout", observe_second_connection)
        event.remove(app.state.engine, "after_cursor_execute", hold_first_write_lock)
        event.remove(second_app.state.engine, "before_cursor_execute", observe_second_write_attempt)
        second_app.state.engine.dispose()


@pytest.mark.parametrize("operation", ["create", "status"])
def test_busy_incident_writes_return_a_temporary_failure_and_leave_no_partial_changes(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    equipment_payload: dict[str, object],
    operation: str,
) -> None:
    equipment = client.post("/api/equipment", json=equipment_payload).json()
    incident_payload = {
        "equipment_id": equipment["id"],
        "title": "Incidencia ficticia",
        "blocking": True,
    }
    original: dict[str, object] | None = None
    if operation == "status":
        response = client.post("/api/incidents", json=incident_payload)
        assert response.status_code == 201
        original = response.json()
        url = f"/api/incidents/{original['id']}/status"
        body = {"status": "resolved", "resolution": "Reparación ficticia"}
        method = "patch"
    else:
        url = "/api/incidents"
        body = incident_payload
        method = "post"

    second_app = create_app(settings.model_copy(update={"sqlite_busy_timeout_ms": 25}))
    try:
        with TestClient(second_app) as second_client:
            authenticate(second_client)
            with app.state.engine.connect() as lock_owner:
                lock_owner.exec_driver_sql("BEGIN IMMEDIATE")
                response = second_client.request(method, url, json=body)
                assert response.status_code == 503
                assert response.headers["retry-after"] == "1"
                assert isinstance(response.json()["detail"], str)
                assert client.get("/api/incidents").json() == (
                    [original] if original is not None else []
                )
                lock_owner.rollback()
            retried = second_client.request(method, url, json=body)
            assert retried.status_code == (201 if operation == "create" else 200)
            assert retried.json()["status"] == ("open" if operation == "create" else "resolved")
            assert len(client.get("/api/incidents").json()) == 1
    finally:
        second_app.state.engine.dispose()


@pytest.mark.parametrize("operation", ["create", "status"])
def test_reader_blocked_commit_rolls_back_incident_creation_or_status_change(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    equipment_payload: dict[str, object],
    operation: str,
) -> None:
    equipment = client.post("/api/equipment", json=equipment_payload).json()
    incident_payload = {"equipment_id": equipment["id"], "title": "Incidencia ficticia"}
    original: dict[str, object] | None = None
    if operation == "status":
        response = client.post("/api/incidents", json=incident_payload)
        assert response.status_code == 201
        original = response.json()
        url = f"/api/incidents/{original['id']}/status"
        body = {"status": "resolved", "resolution": "Reparación ficticia"}
        method = "patch"
    else:
        url = "/api/incidents"
        body = incident_payload
        method = "post"
    second_app = create_app(settings.model_copy(update={"sqlite_busy_timeout_ms": 25}))
    try:
        with TestClient(second_app) as second_client:
            authenticate(second_client)
            with app.state.engine.connect() as reader:
                reader.exec_driver_sql("BEGIN")
                reader.exec_driver_sql("SELECT id FROM equipment").all()
                response = second_client.request(method, url, json=body)
                assert response.status_code == 503
                assert response.headers["retry-after"] == "1"
                assert client.get("/api/incidents").json() == (
                    [original] if original is not None else []
                )
                reader.rollback()
            retried = second_client.request(method, url, json=body)
            assert retried.status_code == (201 if operation == "create" else 200)
            assert len(client.get("/api/incidents").json()) == 1
    finally:
        second_app.state.engine.dispose()
