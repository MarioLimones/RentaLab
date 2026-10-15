"""Portal, administration and CSV must share one definitive reservation lock."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.engine import Connection, ExecutionContext
from test_admin_connected import DATES, sign_in
from test_admin_connected import connected_world as connected_world

from rentalab.clock import get_today_provider
from rentalab.config import Settings
from rentalab.main import create_app
from rentalab.reservations.models import Reservation


@pytest.mark.parametrize("management_source", ["admin", "csv"])
@pytest.mark.parametrize("portal_first", [True, False])
def test_portal_and_management_cannot_confirm_incompatible_reservations(
    app: FastAPI,
    settings: Settings,
    connected_world: tuple,
    management_source: str,
    portal_first: bool,
) -> None:
    customer, other_customer, admin, owner_id, equipment_id = connected_world
    second_app = create_app(settings)
    second_app.dependency_overrides[get_today_provider] = app.dependency_overrides[
        get_today_provider
    ]
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
            assert second_attempted_write.wait(timeout=5), "Second writer never attempted SQL"

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

    def portal_request(browser: TestClient):
        return browser.post("/api/me/reservations", json={"equipment_id": equipment_id, **DATES})

    def management_request(browser: TestClient):
        if management_source == "admin":
            return browser.post(
                "/api/reservations",
                json={
                    "equipment_id": equipment_id,
                    "customer_name": "PRIVATE-MANAGEMENT-RACE-CANARY",
                    "customer_email": "management-race@example.test",
                    **DATES,
                },
            )
        content = (
            "external_reference,customer_name,customer_email,equipment_code,starts_on,ends_on\n"
            "F-RACE,PRIVATE-MANAGEMENT-RACE-CANARY,management-race@example.test,"
            f"CAM-001,{DATES['start_date']},{DATES['end_date']}\n"
        ).encode()
        return browser.post("/api/imports", files={"file": ("race.csv", content, "text/csv")})

    try:
        with TestClient(second_app) as second_browser:
            sign_in(
                second_browser,
                "admin-phase-e@example.test" if portal_first else "one-phase-e@example.test",
            )
            # Authenticate before observing SQL, so only the reservation race is synchronized.
            event.listen(app.state.engine, "checkout", observe_first_connection)
            event.listen(second_app.state.engine, "checkout", observe_second_connection)
            event.listen(app.state.engine, "after_cursor_execute", hold_first_write_lock)
            event.listen(
                second_app.state.engine, "before_cursor_execute", observe_second_write_attempt
            )
            try:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    first = executor.submit(
                        portal_request if portal_first else management_request,
                        customer if portal_first else admin,
                    )
                    assert first_has_lock.wait(timeout=5), "First writer did not acquire SQL lock"
                    second = executor.submit(
                        management_request if portal_first else portal_request, second_browser
                    )
                    first_response = first.result(timeout=10)
                    second_response = second.result(timeout=10)
            finally:
                event.remove(app.state.engine, "checkout", observe_first_connection)
                event.remove(second_app.state.engine, "checkout", observe_second_connection)
                event.remove(app.state.engine, "after_cursor_execute", hold_first_write_lock)
                event.remove(
                    second_app.state.engine, "before_cursor_execute", observe_second_write_attempt
                )
        portal = first_response if portal_first else second_response
        management = second_response if portal_first else first_response
        assert portal.status_code == (201 if portal_first else 409)
        if not portal_first:
            assert "consulta la disponibilidad" in portal.json()["detail"]
            assert "PRIVATE-MANAGEMENT-RACE-CANARY" not in portal.text
            assert "management-race@example.test" not in portal.text
            assert "retry-after" not in portal.headers
        if management_source == "admin":
            assert management.status_code == (409 if portal_first else 201)
            assert "retry-after" not in management.headers
        else:
            # CSV preserves its partial-report contract: a conflicting row is rejected
            # inside HTTP 200, and no extra reservation or reference is persisted.
            assert management.status_code == 200
            report = management.json()
            assert report["totals"] == {
                "total": 1,
                "accepted": 0 if portal_first else 1,
                "already_imported": 0,
                "rejected": 1 if portal_first else 0,
            }
            assert report["rows"][0]["status"] == ("rejected" if portal_first else "accepted")
            if portal_first:
                assert report["rows"][0]["reservation"] is None
        assert first_connections and second_connections
        assert first_connections.isdisjoint(second_connections)
        with app.state.session_factory() as session:
            persisted = session.scalars(select(Reservation)).all()
            assert len(persisted) == 1
            reservation = persisted[0]
            assert reservation.status == "confirmed"
            assert reservation.origin == ("portal" if portal_first else management_source)
            assert reservation.customer_user_id == (owner_id if portal_first else None)
            assert reservation.external_reference == (
                "F-RACE" if not portal_first and management_source == "csv" else None
            )
        assert customer.get("/api/me/reservations").json() == (
            [portal.json()] if portal_first else []
        )
        assert other_customer.get("/api/me/reservations").json() == []
        assert len(admin.get("/api/reservations").json()) == 1
        availability = customer.get(
            f"/api/public/equipment/{equipment_id}/availability", params=DATES
        )
        assert availability.json()["available"] is False
    finally:
        second_app.state.engine.dispose()
