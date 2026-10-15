from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from conftest import authenticate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, ExceptionContext, ExecutionContext

from rentalab.config import Settings
from rentalab.main import create_app

HEADER = "external_reference,customer_name,customer_email,equipment_code,starts_on,ends_on\n"


@pytest.mark.parametrize("changed_data", [False, True])
def test_concurrent_imports_with_the_same_reference_are_atomic_and_idempotent(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    equipment_payload: dict[str, object],
    changed_data: bool,
) -> None:
    assert client.post("/api/equipment", json=equipment_payload).status_code == 201
    first_content = (
        HEADER + "ORDER-1,Cliente ficticio,cliente@example.test,CAM-001,2026-11-10,2026-11-12\n"
    ).encode()
    second_content = (
        HEADER
        + (
            "ORDER-1,Otro cliente,cliente@example.test,CAM-001,2026-11-10,2026-11-12\n"
            if changed_data
            else "ORDER-1,Cliente ficticio,cliente@example.test,CAM-001,2026-11-10,2026-11-12\n"
        )
    ).encode()
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
            assert second_attempted_write.wait(timeout=5), "Second importer never attempted SQL"

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
            first = executor.submit(
                client.post,
                "/api/imports",
                files={"file": ("orders.csv", first_content, "text/csv")},
            )
            assert first_has_lock.wait(timeout=5), "Import did not acquire SQLite write lock"
            second = executor.submit(
                second_client.post,
                "/api/imports",
                files={"file": ("orders.csv", second_content, "text/csv")},
            )
            first_response = first.result(timeout=10)
            second_response = second.result(timeout=10)
        assert first_response.status_code == second_response.status_code == 200
        first_report = first_response.json()
        second_report = second_response.json()
        assert first_report["totals"] == {
            "total": 1,
            "accepted": 1,
            "already_imported": 0,
            "rejected": 0,
        }
        if changed_data:
            assert second_report["totals"] == {
                "total": 1,
                "accepted": 0,
                "already_imported": 0,
                "rejected": 1,
            }
            assert second_report["rows"][0]["reservation"] is None
        else:
            assert second_report["totals"] == {
                "total": 1,
                "accepted": 0,
                "already_imported": 1,
                "rejected": 0,
            }
            assert first_report["rows"][0]["reservation"] == second_report["rows"][0]["reservation"]
        assert first_connections and second_connections
        assert first_connections.isdisjoint(second_connections)
        assert client.get("/api/reservations").json() == [first_report["rows"][0]["reservation"]]
        with app.state.engine.connect() as connection:
            count = connection.scalar(text("SELECT COUNT(*) FROM reservations"))
        assert count == 1
    finally:
        event.remove(app.state.engine, "checkout", observe_first_connection)
        event.remove(second_app.state.engine, "checkout", observe_second_connection)
        event.remove(app.state.engine, "after_cursor_execute", hold_first_write_lock)
        event.remove(second_app.state.engine, "before_cursor_execute", observe_second_write_attempt)
        second_app.state.engine.dispose()


def test_a_busy_row_is_rejected_and_the_next_row_uses_a_clean_transaction(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    equipment_payload: dict[str, object],
) -> None:
    assert client.post("/api/equipment", json=equipment_payload).status_code == 201
    content = (
        HEADER
        + "BUSY-ROW,Cliente ficticio,cliente@example.test,CAM-001,2026-11-10,2026-11-12\n"
        + "NEXT-ROW,Cliente ficticio,cliente@example.test,CAM-001,2026-11-10,2026-11-12\n"
    ).encode()
    second_app = create_app(settings.model_copy(update={"sqlite_busy_timeout_ms": 25}))
    first_failed = Event()
    try:
        with TestClient(second_app) as second_client, app.state.engine.connect() as lock_owner:
            authenticate(second_client)
            lock_owner.exec_driver_sql("BEGIN IMMEDIATE")

            def release_lock_after_first_busy(context: ExceptionContext) -> None:
                if (context.statement or "").strip().upper() == "BEGIN IMMEDIATE":
                    assert not first_failed.is_set()
                    assert getattr(context.original_exception, "sqlite_errorcode", 0) & 0xFF == 5
                    lock_owner.rollback()
                    first_failed.set()

            event.listen(second_app.state.engine, "handle_error", release_lock_after_first_busy)
            try:
                response = second_client.post(
                    "/api/imports", files={"file": ("orders.csv", content, "text/csv")}
                )
            finally:
                event.remove(second_app.state.engine, "handle_error", release_lock_after_first_busy)
            assert first_failed.is_set(), "No real SQLite busy error was observed"
            assert response.status_code == 200
            report = response.json()
            assert report["totals"] == {
                "total": 2,
                "accepted": 1,
                "already_imported": 0,
                "rejected": 1,
            }
            assert [row["status"] for row in report["rows"]] == ["rejected", "accepted"]
            assert report["rows"][0]["reservation"] is None
            assert isinstance(report["rows"][0]["message"], str)
            reservations = client.get("/api/reservations").json()
            assert len(reservations) == 1
            assert reservations[0]["external_reference"] == "NEXT-ROW"
    finally:
        second_app.state.engine.dispose()
