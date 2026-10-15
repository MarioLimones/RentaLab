from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.engine import Connection, ExecutionContext
from test_me_reservations import TODAY, CustomerWorld, login_customer
from test_me_reservations import customer_world as customer_world

from rentalab.clock import get_today_provider
from rentalab.config import Settings
from rentalab.main import create_app
from rentalab.reservations.models import Reservation


def test_two_customers_using_distinct_connections_cannot_double_book(
    app: FastAPI, settings: Settings, customer_world: CustomerWorld
) -> None:
    world = customer_world
    second_app = create_app(settings)
    second_app.dependency_overrides[get_today_provider] = lambda: lambda: TODAY
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
            assert second_attempted_write.wait(timeout=5), "Second customer did not attempt SQL"

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

    try:
        with TestClient(second_app) as second_browser:
            login_customer(second_browser, "bruno@example.test")
            # Observe real SQL only after authentication has issued the two customer sessions.
            event.listen(app.state.engine, "checkout", observe_first_connection)
            event.listen(second_app.state.engine, "checkout", observe_second_connection)
            event.listen(app.state.engine, "after_cursor_execute", hold_first_write_lock)
            event.listen(
                second_app.state.engine, "before_cursor_execute", observe_second_write_attempt
            )
            try:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    first = executor.submit(
                        world.first.post, "/api/me/reservations", json=world.payload()
                    )
                    assert first_has_lock.wait(timeout=5), "First customer did not acquire lock"
                    second = executor.submit(
                        second_browser.post, "/api/me/reservations", json=world.payload()
                    )
                    responses = [first.result(timeout=10), second.result(timeout=10)]
            finally:
                event.remove(app.state.engine, "checkout", observe_first_connection)
                event.remove(second_app.state.engine, "checkout", observe_second_connection)
                event.remove(app.state.engine, "after_cursor_execute", hold_first_write_lock)
                event.remove(
                    second_app.state.engine, "before_cursor_execute", observe_second_write_attempt
                )
        assert [response.status_code for response in responses] == [201, 409]
        assert "consulta la disponibilidad" in responses[1].json()["detail"]
        assert "retry-after" not in responses[1].headers
        assert first_connections and second_connections
        assert first_connections.isdisjoint(second_connections)
        with app.state.session_factory() as session:
            reservations = session.scalars(select(Reservation)).all()
            assert len(reservations) == 1
            reservation = reservations[0]
            assert reservation.status == "confirmed"
            assert reservation.customer_user_id == world.first_id
            assert reservation.customer_name == "Alicia Prueba"
            assert reservation.customer_email == "alicia@example.test"
        assert world.second.get("/api/me/reservations").json() == []
    finally:
        second_app.state.engine.dispose()


@pytest.mark.parametrize("operation", ["create", "cancel"])
def test_business_day_is_read_after_waiting_for_the_sqlite_write_lock(
    app: FastAPI, settings: Settings, customer_world: CustomerWorld, operation: str
) -> None:
    world = customer_world
    existing = world.create() if operation == "cancel" else None
    url = (
        f"/api/me/reservations/{existing['id']}/cancel"
        if existing is not None
        else "/api/me/reservations"
    )
    second_app = create_app(settings)
    day = [date(2026, 11, 9)]
    requested_days: list[date] = []

    def business_day() -> date:
        requested_days.append(day[0])
        return day[0]

    second_app.dependency_overrides[get_today_provider] = lambda: business_day
    attempted_write = Event()

    def observe_write(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            attempted_write.set()

    try:
        with TestClient(second_app) as browser:
            login_customer(browser, "alicia@example.test")
            with app.state.engine.connect() as lock_owner:
                lock_owner.exec_driver_sql("BEGIN IMMEDIATE")
                event.listen(second_app.state.engine, "before_cursor_execute", observe_write)
                try:
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        pending = executor.submit(
                            browser.post, url, json=world.payload() if operation == "create" else {}
                        )
                        assert attempted_write.wait(timeout=5), "Customer did not attempt SQL"
                        assert requested_days == []
                        # A new Madrid day begins while the HTTP request is waiting for SQLite.
                        day[0] = date(2026, 11, 11)
                        lock_owner.rollback()
                        response = pending.result(timeout=10)
                finally:
                    event.remove(second_app.state.engine, "before_cursor_execute", observe_write)
        assert response.status_code == 409, response.text
        assert requested_days == [date(2026, 11, 11)]
        with app.state.session_factory() as session:
            reservations = session.scalars(select(Reservation)).all()
            assert len(reservations) == (1 if operation == "cancel" else 0)
            if reservations:
                assert reservations[0].status == "confirmed"
    finally:
        second_app.state.engine.dispose()
