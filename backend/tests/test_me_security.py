"""HTTP security regression checks for the customer namespace.

These requests deliberately bypass React and use two independent customer cookies.
All accounts, credentials and records belong to the disposable database fixture.
"""

from collections.abc import Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date

import pytest
from conftest import TEST_PASSWORD, TEST_PASSWORD_HASH
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from rentalab.auth.models import User
from rentalab.incidents.models import Incident
from rentalab.reservations.models import Reservation

RESERVATION_FIELDS = {"id", "equipment_id", "start_date", "end_date", "status"}
INCIDENT_FIELDS = {"id", "reservation_id", "title", "description", "status", "public_response"}


def sign_in(browser: TestClient, email: str) -> None:
    csrf = browser.get("/api/auth/csrf")
    assert csrf.status_code == 200
    response = browser.post(
        "/api/auth/login",
        json={"username": email, "password": TEST_PASSWORD},
        headers={"X-CSRF-Token": csrf.json()["csrf_token"]},
    )
    assert response.status_code == 200, response.text
    browser.headers["X-CSRF-Token"] = browser.get("/api/auth/csrf").json()["csrf_token"]


@dataclass
class Customers:
    alice: TestClient
    bob: TestClient
    admin: TestClient
    alice_id: int
    bob_id: int
    admin_id: int
    equipment_id: int

    def reserve(self, browser: TestClient, start: str = "2026-11-10") -> dict:
        response = browser.post(
            "/api/me/reservations",
            json={
                "equipment_id": self.equipment_id,
                "start_date": start,
                "end_date": "2026-11-12",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    def report(self, browser: TestClient, reservation_id: int) -> dict:
        response = browser.post(
            f"/api/me/reservations/{reservation_id}/incidents",
            json={"title": "Aviso propio", "description": "Descripción aportada por el cliente"},
        )
        assert response.status_code == 201, response.text
        return response.json()


@pytest.fixture
def customers(app: FastAPI) -> Iterator[Customers]:
    from rentalab.clock import get_today_provider

    app.dependency_overrides[get_today_provider] = lambda: lambda: date(2026, 11, 1)
    with app.state.session_factory() as database_session:
        records = [
            User(
                name=name,
                email=email,
                password_hash=TEST_PASSWORD_HASH,
                role=role,
                active=True,
            )
            for name, email, role in [
                ("Alice privada", "alice@example.test", "customer"),
                ("Bob privado", "bob@example.test", "customer"),
                ("Administradora", "admin@example.test", "admin"),
            ]
        ]
        database_session.add_all(records)
        database_session.commit()
        ids = [record.id for record in records]
    with ExitStack() as stack:
        alice, bob, admin = [stack.enter_context(TestClient(app)) for _ in range(3)]
        for browser, email in [
            (alice, "alice@example.test"),
            (bob, "bob@example.test"),
            (admin, "admin@example.test"),
        ]:
            sign_in(browser, email)
        equipment = admin.post(
            "/api/equipment",
            json={
                "code": "PRIVATE-CODE-CANARY",
                "name": "Cámara de pruebas",
                "category": "Cámaras",
                "description": "INTERNAL-EQUIPMENT-CANARY",
            },
        )
        assert equipment.status_code == 201, equipment.text
        yield Customers(alice, bob, admin, *ids, equipment.json()["id"])
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/me/reservations"),
        ("POST", "/api/me/reservations"),
        ("GET", "/api/me/reservations/1"),
        ("POST", "/api/me/reservations/1/cancel"),
        ("POST", "/api/me/reservations/1/incidents"),
        ("GET", "/api/me/incidents"),
        ("GET", "/api/me/incidents/1"),
    ],
)
def test_customer_namespace_requires_a_session_before_validating_body(
    app: FastAPI, method: str, path: str
) -> None:
    with TestClient(app) as anonymous:
        response = anonymous.request(method, path, content=b"invalid-json")
        assert response.status_code == 401
        assert set(response.json()) == {"detail"}
        assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/me/reservations"),
        ("POST", "/api/me/reservations"),
        ("GET", "/api/me/reservations/1"),
        ("POST", "/api/me/reservations/1/cancel"),
        ("POST", "/api/me/reservations/1/incidents"),
        ("GET", "/api/me/incidents"),
        ("GET", "/api/me/incidents/1"),
    ],
)
def test_persisted_administrator_uses_management_routes(
    customers: Customers, method: str, path: str
) -> None:
    response = customers.admin.request(method, path, json={})
    assert response.status_code == 403


def test_reservation_lists_and_direct_ids_are_isolated(app: FastAPI, customers: Customers) -> None:
    reservation = customers.reserve(customers.alice)
    assert set(reservation) == RESERVATION_FIELDS
    assert customers.alice.get("/api/me/reservations").json() == [reservation]
    assert customers.bob.get("/api/me/reservations").json() == []
    assert customers.alice.get(f"/api/me/reservations/{reservation['id']}").json() == reservation
    for suffix in ["", "/cancel", "/incidents"]:
        method = "GET" if not suffix else "POST"
        body = (
            {"title": "Ataque", "description": "No es su reserva"}
            if suffix == "/incidents"
            else None
        )
        path = f"/api/me/reservations/{reservation['id']}{suffix}"
        response = customers.bob.request(method, path, json=body)
        nonexistent = customers.bob.request(
            method, f"/api/me/reservations/999999{suffix}", json=body
        )
        assert response.status_code == nonexistent.status_code == 404
        assert response.json() == nonexistent.json()
        assert "Alice" not in response.text
    with app.state.session_factory() as database_session:
        record = database_session.get(Reservation, reservation["id"])
        assert record.status == "confirmed"
        assert record.customer_user_id == customers.alice_id
        assert record.customer_name == "Alice privada"
        assert record.customer_email == "alice@example.test"
        assert record.external_reference is None
        assert database_session.scalar(select(Incident.id)) is None


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("id", 999),
        ("customer_id", 2),
        ("customer_user_id", 2),
        ("user_id", 2),
        ("customer_name", "Identidad falsificada"),
        ("customer_email", "bob@example.test"),
        ("status", "cancelled"),
        ("origin", "csv"),
        ("source", "admin"),
        ("external_reference", "PRIVATE-REFERENCE-CANARY"),
        ("role", "admin"),
    ],
)
def test_customer_reservation_creation_rejects_identity_and_administrative_fields(
    app: FastAPI, customers: Customers, key: str, value: object
) -> None:
    response = customers.alice.post(
        "/api/me/reservations",
        json={
            "equipment_id": customers.equipment_id,
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
            key: value,
        },
    )
    assert response.status_code == 422
    with app.state.session_factory() as database_session:
        assert database_session.scalar(select(Reservation.id)) is None


@pytest.mark.parametrize("key", ["status", "customer_user_id", "equipment_id", "role"])
def test_customer_cancellation_rejects_a_nonempty_body(
    app: FastAPI, customers: Customers, key: str
) -> None:
    reservation = customers.reserve(customers.alice)
    response = customers.alice.post(
        f"/api/me/reservations/{reservation['id']}/cancel", json={key: 1}
    )
    assert response.status_code == 422
    with app.state.session_factory() as database_session:
        assert database_session.get(Reservation, reservation["id"]).status == "confirmed"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("id", 999),
        ("reservation_id", 999),
        ("equipment_id", 999),
        ("customer_user_id", 2),
        ("author_user_id", 2),
        ("customer_id", 2),
        ("priority", "high"),
        ("blocking", True),
        ("status", "resolved"),
        ("resolution", "Resolución falsificada"),
        ("public_response", "Respuesta falsificada"),
        ("internal_notes", "Notas falsificadas"),
    ],
)
def test_customer_incident_rejects_identity_and_administrative_fields(
    app: FastAPI, customers: Customers, key: str, value: object
) -> None:
    reservation = customers.reserve(customers.alice)
    response = customers.alice.post(
        f"/api/me/reservations/{reservation['id']}/incidents",
        json={"title": "Aviso", "description": "Descripción", key: value},
    )
    assert response.status_code == 422
    with app.state.session_factory() as database_session:
        assert database_session.scalar(select(Incident.id)) is None


def test_incident_ownership_and_response_projection_exclude_internal_administration(
    app: FastAPI, customers: Customers
) -> None:
    reservation = customers.reserve(customers.alice)
    incident = customers.report(customers.alice, reservation["id"])
    assert set(incident) == INCIDENT_FIELDS
    assert incident["status"] == "open"
    assert incident["public_response"] == ""
    assert customers.alice.get("/api/me/incidents").json() == [incident]
    assert customers.bob.get("/api/me/incidents").json() == []
    missing = customers.bob.get("/api/me/incidents/999999")
    foreign = customers.bob.get(f"/api/me/incidents/{incident['id']}")
    assert missing.status_code == foreign.status_code == 404
    assert missing.json() == foreign.json()
    with app.state.session_factory() as database_session:
        record = database_session.get(Incident, incident["id"])
        assert record.author_user_id == customers.alice_id
        assert record.equipment_id == customers.equipment_id
        assert record.reservation_id == reservation["id"]
        assert record.blocking is False
        assert record.priority == "medium"
    updated = customers.admin.patch(
        f"/api/incidents/{incident['id']}",
        json={
            "priority": "high",
            "blocking": True,
            "public_response": "Hemos atendido su aviso.",
            "internal_notes": "INTERNAL-NOTES-CANARY",
        },
    )
    assert updated.status_code == 200, updated.text
    resolved = customers.admin.patch(
        f"/api/incidents/{incident['id']}/status",
        json={"status": "resolved", "resolution": "INTERNAL-RESOLUTION-CANARY"},
    )
    assert resolved.status_code == 200, resolved.text
    own = customers.alice.get(f"/api/me/incidents/{incident['id']}")
    assert own.status_code == 200
    assert set(own.json()) == INCIDENT_FIELDS
    assert own.json()["status"] == "resolved"
    assert own.json()["public_response"] == "Hemos atendido su aviso."
    for response in [own, customers.alice.get("/api/me/incidents")]:
        assert "INTERNAL-" not in response.text
        assert "PRIVATE-" not in response.text
        assert "bob@example.test" not in response.text
        assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("token_kind", ["missing", "invalid", "other_customer"])
def test_customer_writes_require_their_own_current_csrf_token(
    app: FastAPI, customers: Customers, token_kind: str
) -> None:
    reservation = customers.reserve(customers.alice)
    csrf = {
        "missing": "",
        "invalid": "incorrect",
        "other_customer": customers.bob.headers["X-CSRF-Token"],
    }[token_kind]
    for path, body in [
        (
            "/api/me/reservations",
            {
                "equipment_id": customers.equipment_id,
                "start_date": "2026-11-15",
                "end_date": "2026-11-17",
            },
        ),
        (f"/api/me/reservations/{reservation['id']}/cancel", {}),
        (
            f"/api/me/reservations/{reservation['id']}/incidents",
            {"title": "Aviso sin CSRF", "description": "No debe crearse"},
        ),
    ]:
        response = customers.alice.post(path, json=body, headers={"X-CSRF-Token": csrf})
        assert response.status_code == 403
    with app.state.session_factory() as database_session:
        assert len(database_session.scalars(select(Reservation)).all()) == 1
        assert database_session.get(Reservation, reservation["id"]).status == "confirmed"
        assert database_session.scalar(select(Incident.id)) is None


def test_current_profile_is_read_from_database_when_creating_reservation(
    app: FastAPI, customers: Customers
) -> None:
    with app.state.session_factory() as database_session:
        user = database_session.get(User, customers.alice_id)
        user.name = "Nombre actualizado"
        user.email = "updated@example.test"
        database_session.commit()
    reservation = customers.reserve(customers.alice)
    with app.state.session_factory() as database_session:
        record = database_session.get(Reservation, reservation["id"])
        assert record.customer_user_id == customers.alice_id
        assert record.customer_name == "Nombre actualizado"
        assert record.customer_email == "updated@example.test"


@pytest.mark.parametrize("change", ["inactive", "role", "expired"])
def test_customer_access_uses_current_account_and_session_state(
    app: FastAPI, customers: Customers, change: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if change == "expired":
        monkeypatch.setattr("rentalab.auth.service.current_timestamp", lambda: 4_000_000_000)
    else:
        with app.state.session_factory() as database_session:
            user = database_session.get(User, customers.alice_id)
            if change == "inactive":
                user.active = False
            else:
                user.role = "admin"
            database_session.commit()
    expected = 403 if change == "role" else 401
    assert customers.alice.get("/api/me/reservations").status_code == expected
    assert customers.alice.get("/api/me/incidents").status_code == expected
    assert (
        customers.alice.post(
            "/api/me/reservations",
            json={
                "equipment_id": customers.equipment_id,
                "start_date": "2026-11-10",
                "end_date": "2026-11-12",
            },
        ).status_code
        == expected
    )


def test_legacy_management_cannot_leak_customer_internal_fields(customers: Customers) -> None:
    reservation = customers.reserve(customers.alice)
    incident = customers.report(customers.alice, reservation["id"])
    for path in [
        "/api/reservations",
        f"/api/reservations/{reservation['id']}",
        f"/api/reservations/{reservation['id']}/",
        "/api/incidents",
        f"/api/incidents/{incident['id']}",
        f"/api/incidents/{incident['id']}/",
        "/api/equipment",
        f"/api/equipment/{customers.equipment_id}",
    ]:
        for browser in [customers.alice, customers.bob]:
            response = browser.get(path)
            assert response.status_code == 403, (path, response.text)
            assert "INTERNAL-" not in response.text
            assert "PRIVATE-" not in response.text
    for browser in [customers.alice, customers.bob]:
        for method, path, body in [
            ("POST", f"/api/reservations/{reservation['id']}/cancel", {}),
            ("PATCH", f"/api/incidents/{incident['id']}", {"blocking": True}),
            (
                "PATCH",
                f"/api/incidents/{incident['id']}/status",
                {"status": "resolved", "resolution": "Resolución falsificada"},
            ),
            ("PATCH", f"/api/me/incidents/{incident['id']}", {"blocking": True}),
        ]:
            response = browser.request(method, path, json=body)
            assert response.status_code in {403, 405}, (path, response.text)


def test_historical_email_match_stays_unowned_and_visible_to_administrator(
    app: FastAPI, customers: Customers
) -> None:
    response = customers.admin.post(
        "/api/reservations",
        json={
            "equipment_id": customers.equipment_id,
            "customer_name": "Alice privada",
            "customer_email": "alice@example.test",
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
            "external_reference": "PRIVATE-REFERENCE-CANARY",
        },
    )
    assert response.status_code == 201
    reservation_id = response.json()["id"]
    with app.state.session_factory() as database_session:
        historical = Incident(
            equipment_id=customers.equipment_id,
            title="Aviso histórico",
            description="INTERNAL-OLD-INCIDENT-CANARY",
            author_user_id=None,
        )
        database_session.add(historical)
        database_session.commit()
        incident_id = historical.id
        assert database_session.get(Reservation, reservation_id).customer_user_id is None
    for browser in [customers.alice, customers.bob]:
        assert browser.get("/api/me/reservations").json() == []
        assert browser.get("/api/me/incidents").json() == []
        assert browser.get(f"/api/me/reservations/{reservation_id}").status_code == 404
        assert browser.get(f"/api/me/incidents/{incident_id}").status_code == 404
        assert browser.post(f"/api/me/reservations/{reservation_id}/cancel").status_code == 404
    assert reservation_id in [row["id"] for row in customers.admin.get("/api/reservations").json()]
    assert incident_id in [row["id"] for row in customers.admin.get("/api/incidents").json()]
    assert customers.admin.get(f"/api/reservations/{reservation_id}").status_code == 200
    assert customers.admin.get(f"/api/incidents/{incident_id}").status_code == 200


def test_conflict_after_public_query_never_exposes_other_customer_identity(
    app: FastAPI, customers: Customers
) -> None:
    availability = customers.alice.get(
        f"/api/public/equipment/{customers.equipment_id}/availability",
        params={"start_date": "2026-11-10", "end_date": "2026-11-12"},
    )
    assert availability.status_code == 200
    assert availability.json()["available"] is True
    customers.reserve(customers.bob)
    response = customers.alice.post(
        "/api/me/reservations",
        json={
            "equipment_id": customers.equipment_id,
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
        },
    )
    assert response.status_code == 409
    assert isinstance(response.json()["detail"], str)
    assert "Bob" not in response.text
    assert "bob@example.test" not in response.text
    assert "PRIVATE-" not in response.text
    with app.state.session_factory() as database_session:
        assert len(database_session.scalars(select(Reservation)).all()) == 1


def test_authorship_does_not_grant_access_to_unlinked_or_foreign_reservation_reports(
    app: FastAPI, customers: Customers
) -> None:
    reservation = customers.reserve(customers.bob)
    with app.state.session_factory() as database_session:
        records = [
            Incident(
                equipment_id=customers.equipment_id,
                title="Aviso de autoría histórica",
                description="INTERNAL-UNLINKED-OR-FOREIGN-CANARY",
                author_user_id=customers.alice_id,
                reservation_id=reservation_id,
            )
            for reservation_id in [None, reservation["id"]]
        ]
        database_session.add_all(records)
        database_session.commit()
        ids = [record.id for record in records]
    for browser in [customers.alice, customers.bob]:
        assert browser.get("/api/me/incidents").json() == []
        for incident_id in ids:
            response = browser.get(f"/api/me/incidents/{incident_id}")
            assert response.status_code == 404
            assert "INTERNAL-" not in response.text
    assert set(ids) <= {row["id"] for row in customers.admin.get("/api/incidents").json()}


def test_client_cannot_choose_another_owner_through_query_parameters(customers: Customers) -> None:
    reservation = customers.reserve(customers.alice)
    incident = customers.report(customers.alice, reservation["id"])
    for endpoint in ["reservations", "incidents"]:
        response = customers.bob.get(
            f"/api/me/{endpoint}",
            params={"customer_user_id": customers.alice_id, "author_user_id": customers.alice_id},
        )
        # An unknown filter may be rejected or ignored; it can never change scope.
        assert response.status_code in {200, 422}
        if response.status_code == 200:
            assert response.json() == []
        assert "Alice privada" not in response.text
        assert "Descripción aportada por el cliente" not in response.text
    assert customers.bob.get(f"/api/me/incidents/{incident['id']}").status_code == 404
