"""Connected HTTP journeys against a migrated, disposable SQLite database."""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_admin_connected import DATES, PASSWORD, sign_in
from test_admin_connected import connected_world as connected_world

from rentalab.clock import get_today_provider


def test_visitor_registers_signs_in_and_explicitly_confirms_a_public_equipment(
    app: FastAPI, connected_world: tuple
) -> None:
    _, other_customer, admin, _, equipment_id = connected_world
    changed = admin.patch(
        f"/api/equipment/{equipment_id}",
        json={
            "description": "PRIVATE-INVENTORY-CANARY",
            "public_description": "Cámara para grabaciones en interiores y exteriores.",
            "technical_specs": {"Resolución": "4K", "Autonomía": "120 minutos"},
        },
    )
    assert changed.status_code == 200
    with TestClient(app) as visitor:
        catalogue = visitor.get("/api/public/equipment", params={"q": "CÁMARA"})
        assert catalogue.status_code == 200
        assert [item["id"] for item in catalogue.json()] == [equipment_id]
        equipment = visitor.get(f"/api/public/equipment/{equipment_id}")
        assert equipment.status_code == 200
        assert equipment.json()["technical_specs"] == {
            "Resolución": "4K",
            "Autonomía": "120 minutos",
        }
        assert "PRIVATE-INVENTORY-CANARY" not in equipment.text
        fallback = visitor.get(equipment.json()["image_fallback_url"])
        assert fallback.status_code == 200
        assert fallback.headers["content-type"].startswith("image/svg+xml")
        availability = f"/api/public/equipment/{equipment_id}/availability"
        without_dates = visitor.get(availability).json()
        assert without_dates["status"] == "select_dates"
        assert without_dates["available"] is None
        assert visitor.get(availability, params=DATES).json()["available"] is True

        token = visitor.get("/api/auth/csrf").json()["csrf_token"]
        registered = visitor.post(
            "/api/auth/register",
            json={
                "name": "Cliente del recorrido completo",
                "email": "  FULL-JOURNEY@Example.TEST  ",
                "password": PASSWORD,
            },
            headers={"X-CSRF-Token": token},
        )
        assert registered.status_code == 201
        assert registered.json()["role"] == "customer"
        assert registered.json()["email"] == "full-journey@example.test"
        # Registration and login never create a booking on the user's behalf.
        assert visitor.get("/api/auth/session").status_code == 401
        assert admin.get("/api/reservations").json() == []
        sign_in(visitor, "FULL-JOURNEY@EXAMPLE.TEST")
        session = visitor.get("/api/auth/session")
        assert session.status_code == 200
        assert session.json()["user"] == registered.json()
        assert visitor.get("/api/me/reservations").json() == []

        created = visitor.post("/api/me/reservations", json={"equipment_id": equipment_id, **DATES})
        assert created.status_code == 201
        reservation = created.json()
        private_path = f"/api/me/reservations/{reservation['id']}"
        assert visitor.get(private_path).json() == reservation
        assert visitor.get("/api/me/reservations").json() == [reservation]
        management = admin.get(f"/api/reservations/{reservation['id']}").json()
        assert management["customer_user_id"] == registered.json()["id"]
        assert management["customer_name"] == "Cliente del recorrido completo"
        assert management["customer_email"] == "full-journey@example.test"
        assert management["origin"] == "portal"
        assert other_customer.get(private_path).status_code == 404
        assert visitor.get(availability, params=DATES).json()["available"] is False


@pytest.mark.parametrize(
    ("role", "today", "expected_status"),
    [
        ("customer", date(2030, 11, 19), 200),
        ("customer", date(2030, 11, 20), 409),
        ("admin", date(2030, 11, 20), 200),
        ("admin", date(2030, 11, 23), 200),
    ],
)
def test_cancellation_frees_only_its_interval_under_each_roles_policy(
    app: FastAPI,
    connected_world: tuple,
    role: str,
    today: date,
    expected_status: int,
) -> None:
    customer, second, admin, owner_id, equipment_id = connected_world
    created = customer.post("/api/me/reservations", json={"equipment_id": equipment_id, **DATES})
    assert created.status_code == 201
    reservation = created.json()
    adjacent_dates = {"start_date": DATES["end_date"], "end_date": "2030-11-23"}
    adjacent = second.post(
        "/api/me/reservations", json={"equipment_id": equipment_id, **adjacent_dates}
    )
    assert adjacent.status_code == 201
    app.dependency_overrides[get_today_provider] = lambda: lambda: today
    browser = customer if role == "customer" else admin
    namespace = "/api/me/reservations" if role == "customer" else "/api/reservations"
    cancelled = browser.post(f"{namespace}/{reservation['id']}/cancel")
    assert cancelled.status_code == expected_status
    state = "cancelled" if expected_status == 200 else "confirmed"
    expected = {**reservation, "status": state}
    assert customer.get(f"/api/me/reservations/{reservation['id']}").json() == expected
    assert customer.get("/api/me/reservations").json() == [expected]
    management = admin.get(f"/api/reservations/{reservation['id']}").json()
    assert management["customer_user_id"] == owner_id
    assert management["origin"] == "portal"
    assert management["status"] == state
    availability = f"/api/public/equipment/{equipment_id}/availability"
    assert customer.get(availability, params=DATES).json()["available"] is (expected_status == 200)
    assert customer.get(availability, params=adjacent_dates).json()["available"] is False
    assert second.get(f"/api/me/reservations/{adjacent.json()['id']}").json() == adjacent.json()
    if expected_status == 200:
        # A successful cancellation remains idempotent after the original start day,
        # including when the administrator was the one who cancelled it.
        app.dependency_overrides[get_today_provider] = lambda: lambda: date(2030, 11, 23)
        assert customer.post(f"/api/me/reservations/{reservation['id']}/cancel").json() == expected
        assert customer.get(availability, params=DATES).json()["available"] is True
