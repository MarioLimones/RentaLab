from collections.abc import Iterator
from contextlib import ExitStack
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rentalab.auth.schemas import RegisterRequest
from rentalab.clock import get_today_provider

PASSWORD = "isolated-phase-e-behaviour-password"
DATES = {"start_date": "2030-11-20", "end_date": "2030-11-22"}


def sign_in(browser: TestClient, email: str) -> None:
    csrf = browser.get("/api/auth/csrf").json()["csrf_token"]
    response = browser.post(
        "/api/auth/login",
        json={"username": email, "password": PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    browser.headers["X-CSRF-Token"] = browser.get("/api/auth/csrf").json()["csrf_token"]


@pytest.fixture
def connected_world(app: FastAPI, equipment_payload: dict) -> Iterator[tuple]:
    app.dependency_overrides[get_today_provider] = lambda: lambda: date(2030, 10, 15)
    identities = [
        ("Cliente Uno", "one-phase-e@example.test", "customer"),
        ("Cliente Dos", "two-phase-e@example.test", "customer"),
        ("Administración", "admin-phase-e@example.test", "admin"),
    ]
    users = [
        app.state.auth_service.register(
            RegisterRequest(name=name, email=email, password=PASSWORD), role=role
        )
        for name, email, role in identities
    ]
    with ExitStack() as stack:
        browsers = [stack.enter_context(TestClient(app)) for _ in identities]
        for browser, (_, email, _) in zip(browsers, identities, strict=True):
            sign_in(browser, email)
        first, second, admin = browsers
        equipment = admin.post("/api/equipment", json=equipment_payload)
        assert equipment.status_code == 201
        yield first, second, admin, users[0].id, equipment.json()["id"]
    app.dependency_overrides.pop(get_today_provider, None)


def test_customer_and_administrator_share_cancellation_communication_and_availability(
    connected_world: tuple,
) -> None:
    first, second, admin, owner_id, equipment_id = connected_world
    initial = first.post(
        "/api/me/reservations",
        json={"equipment_id": equipment_id, "start_date": "2030-11-10", "end_date": "2030-11-12"},
    )
    assert initial.status_code == 201
    reservation_id = initial.json()["id"]
    management = admin.get(f"/api/reservations/{reservation_id}").json()
    assert management["customer_user_id"] == owner_id
    assert management["origin"] == "portal"
    assert management["customer_email"] == "one-phase-e@example.test"
    assert admin.post(f"/api/reservations/{reservation_id}/cancel").status_code == 200
    own = first.get(f"/api/me/reservations/{reservation_id}").json()
    assert own == {**initial.json(), "status": "cancelled"}
    assert second.get(f"/api/me/reservations/{reservation_id}").status_code == 404

    current = first.post(
        "/api/me/reservations",
        json={"equipment_id": equipment_id, "start_date": "2030-11-14", "end_date": "2030-11-16"},
    )
    assert current.status_code == 201
    report = first.post(
        f"/api/me/reservations/{current.json()['id']}/incidents",
        json={"title": "Problema de prueba", "description": "El visor no responde."},
    )
    assert report.status_code == 201
    incident_id = report.json()["id"]
    pending = admin.get(f"/api/incidents/{incident_id}").json()
    assert pending["author_user_id"] == owner_id
    assert pending["reservation_id"] == current.json()["id"]
    assert pending["status"] == "open"
    assert pending["blocking"] is False
    availability_path = f"/api/public/equipment/{equipment_id}/availability"
    assert first.get(availability_path, params=DATES).json()["available"] is True

    updated = admin.patch(
        f"/api/incidents/{incident_id}",
        json={
            "priority": "high",
            "blocking": True,
            "public_response": "Revisaremos el visor contigo.",
            "internal_notes": "Nota privada centinela.",
        },
    )
    assert updated.status_code == 200
    customer_report = first.get(f"/api/me/incidents/{incident_id}").json()
    assert customer_report["public_response"] == "Revisaremos el visor contigo."
    assert "internal_notes" not in customer_report
    assert "resolution" not in customer_report
    assert "Nota privada" not in str(customer_report)
    assert second.get(f"/api/me/incidents/{incident_id}").status_code == 404
    assert first.get(availability_path, params=DATES).json()["available"] is False
    assert (
        second.post(
            "/api/me/reservations", json={"equipment_id": equipment_id, **DATES}
        ).status_code
        == 409
    )
    assert (
        admin.post(
            "/api/reservations",
            json={
                "equipment_id": equipment_id,
                "customer_name": "Intento de gestión",
                "customer_email": "manual@example.test",
                **DATES,
            },
        ).status_code
        == 409
    )

    another = admin.post(
        "/api/incidents",
        json={"equipment_id": equipment_id, "title": "Segundo bloqueo", "blocking": True},
    )
    assert another.status_code == 201
    assert (
        admin.patch(
            f"/api/incidents/{incident_id}/status",
            json={"status": "resolved", "resolution": "Resolución interna del primer aviso."},
        ).status_code
        == 200
    )
    assert first.get(availability_path, params=DATES).json()["available"] is False
    assert (
        second.post(
            "/api/me/reservations", json={"equipment_id": equipment_id, **DATES}
        ).status_code
        == 409
    )

    assert admin.patch(f"/api/equipment/{equipment_id}", json={"active": False}).status_code == 200
    assert (
        admin.patch(
            f"/api/incidents/{another.json()['id']}/status",
            json={"status": "resolved", "resolution": "Segundo bloqueo resuelto."},
        ).status_code
        == 200
    )
    assert (
        admin.get(f"/api/equipment/{equipment_id}/availability", params=DATES).json()["reason"]
        == "equipment_inactive"
    )
    assert first.get(availability_path, params=DATES).status_code == 404
    assert (
        second.post(
            "/api/me/reservations", json={"equipment_id": equipment_id, **DATES}
        ).status_code
        == 409
    )
    assert admin.patch(f"/api/equipment/{equipment_id}", json={"active": True}).status_code == 200
    assert first.get(availability_path, params=DATES).json()["available"] is True
    confirmed = second.post("/api/me/reservations", json={"equipment_id": equipment_id, **DATES})
    assert confirmed.status_code == 201
    resolved = first.get(f"/api/me/incidents/{incident_id}").json()
    assert resolved["status"] == "resolved"
    assert resolved["public_response"] == "Revisaremos el visor contigo."
    assert "Resolución interna" not in str(resolved)
    assert len(admin.get("/api/reservations").json()) == 3


def test_csv_keeps_its_owner_unknown_even_when_a_matching_email_registers(
    app: FastAPI,
    connected_world: tuple,
) -> None:
    _, _, admin, _, _ = connected_world
    content = (
        b"external_reference,customer_name,customer_email,equipment_code,starts_on,ends_on\n"
        b"E-CSV,Nombre del pedido,matching-phase-e@example.test,CAM-001,2030-12-10,2030-12-12\n"
    )
    imported = admin.post("/api/imports", files={"file": ("orders.csv", content, "text/csv")})
    assert imported.status_code == 200
    reservation = imported.json()["rows"][0]["reservation"]
    assert reservation["origin"] == "csv"
    assert reservation["customer_user_id"] is None
    with TestClient(app) as matching:
        csrf = matching.get("/api/auth/csrf").json()["csrf_token"]
        registered = matching.post(
            "/api/auth/register",
            json={
                "name": "Cuenta creada después",
                "email": "matching-phase-e@example.test",
                "password": PASSWORD,
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert registered.status_code == 201
        sign_in(matching, "matching-phase-e@example.test")
        assert matching.get("/api/me/reservations").json() == []
        historical = f"/api/me/reservations/{reservation['id']}"
        missing = matching.get("/api/me/reservations/999999")
        assert matching.get(historical).json() == missing.json()
        assert matching.get(historical).status_code == 404
        denied_cancel = matching.post(f"{historical}/cancel")
        denied_report = matching.post(
            f"{historical}/incidents",
            json={"title": "Intento de apropiación", "description": "Solo coincide el correo."},
        )
        assert denied_cancel.status_code == denied_report.status_code == 404
        assert denied_cancel.json() == denied_report.json() == missing.json()
        assert matching.get("/api/me/incidents").json() == []
    repeated = admin.post("/api/imports", files={"file": ("orders.csv", content, "text/csv")})
    assert repeated.status_code == 200
    assert repeated.json()["rows"][0]["status"] == "already_imported"
    assert repeated.json()["rows"][0]["reservation"] == reservation
    assert admin.get("/api/reservations", params={"origin": "csv"}).json() == [reservation]
