from collections.abc import Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from rentalab.auth.schemas import RegisterRequest
from rentalab.clock import get_today_provider
from rentalab.reservations.models import Reservation

TODAY = date(2026, 10, 15)
CUSTOMER_PASSWORD = "isolated-phase-c-customer-password"


def login_customer(browser: TestClient, email: str) -> None:
    token = browser.get("/api/auth/csrf").json()["csrf_token"]
    response = browser.post(
        "/api/auth/login",
        json={"username": email, "password": CUSTOMER_PASSWORD},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200, response.text
    browser.headers["X-CSRF-Token"] = browser.get("/api/auth/csrf").json()["csrf_token"]


@dataclass
class CustomerWorld:
    first: TestClient
    second: TestClient
    admin: TestClient
    first_id: int
    second_id: int
    equipment_id: int

    def payload(self, **changes: object) -> dict[str, object]:
        return {
            "equipment_id": self.equipment_id,
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
            **changes,
        }

    def create(self, browser: TestClient | None = None, **changes: object) -> dict:
        response = (browser or self.first).post(
            "/api/me/reservations", json=self.payload(**changes)
        )
        assert response.status_code == 201, response.text
        return response.json()


@pytest.fixture
def customer_world(app: FastAPI, equipment_payload: dict) -> Iterator[CustomerWorld]:
    app.dependency_overrides[get_today_provider] = lambda: lambda: TODAY
    identities = [
        ("Alicia Prueba", "alicia@example.test", "customer"),
        ("Bruno Prueba", "bruno@example.test", "customer"),
        ("Administración Prueba", "admin-phase-c@example.test", "admin"),
    ]
    users = [
        app.state.auth_service.register(
            RegisterRequest(name=name, email=email, password=CUSTOMER_PASSWORD), role=role
        )
        for name, email, role in identities
    ]
    with ExitStack() as stack:
        browsers = [stack.enter_context(TestClient(app)) for _identity in identities]
        for browser, (_name, email, _role) in zip(browsers, identities, strict=True):
            login_customer(browser, email)
        first, second, admin = browsers
        equipment = admin.post("/api/equipment", json=equipment_payload)
        assert equipment.status_code == 201, equipment.text
        yield CustomerWorld(first, second, admin, users[0].id, users[1].id, equipment.json()["id"])
    app.dependency_overrides.pop(get_today_provider, None)


def test_create_uses_current_account_and_returns_explicit_minimal_schema(
    app: FastAPI, customer_world: CustomerWorld
) -> None:
    world = customer_world
    response = world.first.post("/api/me/reservations", json=world.payload())
    assert response.status_code == 201, response.text
    actual = response.json()
    assert actual == {"id": actual["id"], **world.payload(), "status": "confirmed"}
    assert response.headers["location"] == f"/api/me/reservations/{actual['id']}"
    assert response.headers["cache-control"] == "no-store"
    assert world.first.get(response.headers["location"]).json() == actual
    with app.state.session_factory() as session:
        row = session.get(Reservation, actual["id"])
        assert row.customer_user_id == world.first_id
        assert row.customer_name == "Alicia Prueba"
        assert row.customer_email == "alicia@example.test"
        assert row.external_reference is None
        assert row.status == "confirmed"
    assert world.admin.get(f"/api/reservations/{actual['id']}").status_code == 200


def test_lists_and_identifiers_isolate_two_customers_and_preserve_unowned_history(
    app: FastAPI, customer_world: CustomerWorld
) -> None:
    world = customer_world
    first = world.create()
    second = world.create(world.second, start_date="2026-11-12", end_date="2026-11-13")
    historical = world.admin.post(
        "/api/reservations",
        json={
            **world.payload(start_date="2026-11-13", end_date="2026-11-14"),
            "customer_name": "Histórico del CSV",
            "customer_email": "alicia@example.test",
            "external_reference": "PRIVATE-HISTORICAL-REFERENCE",
        },
    )
    assert historical.status_code == 201
    cancelled = world.first.post(f"/api/me/reservations/{first['id']}/cancel").json()
    assert world.first.get("/api/me/reservations").json() == [cancelled]
    assert world.second.get("/api/me/reservations").json() == [second]
    for browser, inaccessible in [
        (world.first, [second["id"], historical.json()["id"], 999999]),
        (world.second, [first["id"], historical.json()["id"], 999999]),
    ]:
        missing = browser.get("/api/me/reservations/999999")
        for reservation_id in inaccessible:
            detail = browser.get(f"/api/me/reservations/{reservation_id}")
            cancel = browser.post(f"/api/me/reservations/{reservation_id}/cancel")
            assert detail.status_code == cancel.status_code == 404
            assert detail.json() == cancel.json() == missing.json()
    assert len(world.admin.get("/api/reservations").json()) == 3
    with app.state.session_factory() as session:
        assert session.get(Reservation, historical.json()["id"]).customer_user_id is None
        assert session.get(Reservation, second["id"]).status == "confirmed"


@pytest.mark.parametrize(
    "extra",
    [
        {"customer_user_id": 2},
        {"customer_id": 2},
        {"customer_name": "Falsa identidad"},
        {"customer_email": "bruno@example.test"},
        {"user_id": 2},
        {"id": 4},
        {"status": "cancelled"},
        {"origin": "csv"},
        {"external_reference": "PRIVATE-REFERENCE"},
        {"role": "admin"},
    ],
)
def test_creation_rejects_identity_and_administrative_fields_without_writing(
    app: FastAPI, customer_world: CustomerWorld, extra: dict
) -> None:
    world = customer_world
    response = world.first.post("/api/me/reservations", json={**world.payload(), **extra})
    assert response.status_code == 422, response.text
    with app.state.session_factory() as session:
        assert session.scalar(select(Reservation.id)) is None


@pytest.mark.parametrize(
    "extra",
    [{"status": "confirmed"}, {"customer_user_id": 2}, {"origin": "csv"}, {"equipment_id": 2}],
)
def test_cancellation_rejects_extra_fields_without_mutating(
    app: FastAPI, customer_world: CustomerWorld, extra: dict
) -> None:
    world = customer_world
    reservation = world.create()
    response = world.first.post(f"/api/me/reservations/{reservation['id']}/cancel", json=extra)
    assert response.status_code == 422
    with app.state.session_factory() as session:
        assert session.get(Reservation, reservation["id"]).status == "confirmed"


@pytest.mark.parametrize(
    "changes",
    [
        {"start_date": "2026-11-12", "end_date": "2026-11-12"},
        {"start_date": "2026-11-13", "end_date": "2026-11-12"},
        {"start_date": "2026-02-30"},
        {"start_date": "2026-11-10T00:00:00"},
        {"start_date": 0},
        {"equipment_id": True},
        {"equipment_id": 0},
    ],
)
def test_new_reservations_validate_dates_and_equipment(
    customer_world: CustomerWorld, changes: dict
) -> None:
    world = customer_world
    assert (
        world.first.post("/api/me/reservations", json=world.payload(**changes)).status_code == 422
    )
    assert world.first.get("/api/me/reservations").json() == []


def test_rejects_past_start_but_allows_today(customer_world: CustomerWorld) -> None:
    world = customer_world
    past = world.first.post(
        "/api/me/reservations",
        json=world.payload(start_date="2026-10-14", end_date="2026-10-16"),
    )
    assert past.status_code == 409
    assert "anterior a hoy" in past.json()["detail"]
    reservation = world.create(start_date="2026-10-15", end_date="2026-10-16")
    assert reservation["start_date"] == TODAY.isoformat()


@pytest.mark.parametrize("today", [date(2026, 11, 10), date(2026, 11, 11), date(2026, 12, 1)])
def test_cannot_cancel_on_or_after_start(
    app: FastAPI, customer_world: CustomerWorld, today: date
) -> None:
    world = customer_world
    reservation = world.create()
    app.dependency_overrides[get_today_provider] = lambda: lambda: today
    response = world.first.post(f"/api/me/reservations/{reservation['id']}/cancel")
    assert response.status_code == 409
    assert "antes de su fecha de inicio" in response.json()["detail"]
    assert world.first.get(f"/api/me/reservations/{reservation['id']}").json() == reservation


def test_cancel_is_idempotent_after_start_and_does_not_write_again(
    app: FastAPI, customer_world: CustomerWorld
) -> None:
    world = customer_world
    reservation = world.create()
    url = f"/api/me/reservations/{reservation['id']}/cancel"
    first = world.first.post(url, json={})
    assert first.status_code == 200
    assert first.json()["status"] == "cancelled"
    app.dependency_overrides[get_today_provider] = lambda: lambda: date(2026, 12, 1)
    statements = []

    def observe(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.strip().upper())

    event.listen(app.state.engine, "before_cursor_execute", observe)
    try:
        repeated = world.first.post(url)
    finally:
        event.remove(app.state.engine, "before_cursor_execute", observe)
    assert repeated.status_code == 200
    assert repeated.json() == first.json()
    assert not any(statement.startswith("UPDATE") for statement in statements)
    assert world.first.get("/api/me/reservations").json() == [first.json()]


def test_business_day_uses_madrid_even_when_utc_is_previous_day(
    app: FastAPI, customer_world: CustomerWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = customer_world
    app.dependency_overrides.pop(get_today_provider)
    monkeypatch.setattr(
        "rentalab.clock.utc_now", lambda: datetime(2026, 10, 14, 22, 30, tzinfo=UTC)
    )
    previous_utc_day = world.first.post(
        "/api/me/reservations",
        json=world.payload(start_date="2026-10-14", end_date="2026-10-16"),
    )
    assert previous_utc_day.status_code == 409
    today = world.create(start_date="2026-10-15", end_date="2026-10-16")
    assert world.first.post(f"/api/me/reservations/{today['id']}/cancel").status_code == 409


def test_shared_availability_applies_overlap_adjacency_cancellation_and_blocks(
    customer_world: CustomerWorld,
) -> None:
    world = customer_world
    public = f"/api/public/equipment/{world.equipment_id}/availability"
    interval = {"start_date": "2026-11-10", "end_date": "2026-11-12"}
    assert world.first.get(public, params=interval).json()["available"] is True
    first = world.create()
    overlap = world.second.post("/api/me/reservations", json=world.payload())
    assert overlap.status_code == 409
    assert "consulta la disponibilidad" in overlap.json()["detail"]
    world.create(world.second, start_date="2026-11-12", end_date="2026-11-13")
    assert world.first.post(f"/api/me/reservations/{first['id']}/cancel").status_code == 200
    assert world.first.get(public, params=interval).json()["available"] is True
    incident = world.admin.post(
        "/api/incidents",
        json={
            "equipment_id": world.equipment_id,
            "title": "PRIVATE-BLOCK-TITLE",
            "description": "PRIVATE-BLOCK-DESCRIPTION",
            "blocking": True,
        },
    )
    assert incident.status_code == 201, incident.text
    blocked = world.first.post("/api/me/reservations", json=world.payload())
    assert blocked.status_code == 409
    assert blocked.json() == overlap.json()
    assert "PRIVATE" not in blocked.text
    assert world.first.get(public, params=interval).json()["available"] is False


@pytest.mark.parametrize("active", [False, None])
def test_inactive_or_missing_equipment_cannot_be_reserved(
    customer_world: CustomerWorld, active: bool | None
) -> None:
    world = customer_world
    equipment_id = 999999
    if active is not None:
        equipment_id = world.equipment_id
        assert (
            world.admin.patch(f"/api/equipment/{equipment_id}", json={"active": False}).status_code
            == 200
        )
    response = world.first.post(
        "/api/me/reservations", json=world.payload(equipment_id=equipment_id)
    )
    assert response.status_code == (404 if active is None else 409)
    assert world.first.get("/api/me/reservations").json() == []


@pytest.mark.parametrize("extra_query", [{"customer_user_id": 2}, {"status": "confirmed"}])
def test_list_does_not_accept_owner_or_administrative_query_filters(
    customer_world: CustomerWorld, extra_query: dict
) -> None:
    assert customer_world.first.get("/api/me/reservations", params=extra_query).status_code == 422


def test_missing_session_and_admin_role_have_distinct_http_contracts(
    app: FastAPI, customer_world: CustomerWorld
) -> None:
    world = customer_world
    with TestClient(app) as visitor:
        for browser, expected in [(visitor, 401), (world.admin, 403)]:
            assert browser.get("/api/me/reservations").status_code == expected
            assert browser.get("/api/me/reservations/999999").status_code == expected
            assert (
                browser.post("/api/me/reservations", json=world.payload()).status_code == expected
            )
            assert browser.post("/api/me/reservations/999999/cancel").status_code == expected


@pytest.mark.parametrize("provided_csrf", [None, "wrong-csrf"])
def test_customer_writes_require_csrf_without_mutation(
    customer_world: CustomerWorld, provided_csrf: str | None
) -> None:
    world = customer_world
    reservation = world.create()
    original_csrf = world.first.headers.pop("X-CSRF-Token")
    if provided_csrf is not None:
        world.first.headers["X-CSRF-Token"] = provided_csrf
    try:
        creation = world.first.post(
            "/api/me/reservations",
            json=world.payload(start_date="2026-11-12", end_date="2026-11-13"),
        )
        cancellation = world.first.post(f"/api/me/reservations/{reservation['id']}/cancel")
    finally:
        world.first.headers["X-CSRF-Token"] = original_csrf
    assert creation.status_code == cancellation.status_code == 403
    assert world.first.get("/api/me/reservations").json() == [reservation]
