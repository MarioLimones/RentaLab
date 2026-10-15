from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from rentalab.incidents.models import Incident
from rentalab.reservations.models import Reservation

CUSTOMER_EMAIL = "customer-access@example.test"
CUSTOMER_PASSWORD = "customer-access-password"


def register_customer(browser: TestClient, email: str = CUSTOMER_EMAIL) -> dict[str, object]:
    token = browser.get("/api/auth/csrf").json()["csrf_token"]
    response = browser.post(
        "/api/auth/register",
        json={"name": "Cliente ficticio", "email": email, "password": CUSTOMER_PASSWORD},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def customer(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as browser:
        register_customer(browser)
        token = browser.get("/api/auth/csrf").json()["csrf_token"]
        response = browser.post(
            "/api/auth/login",
            json={"username": CUSTOMER_EMAIL, "password": CUSTOMER_PASSWORD},
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 200, response.text
        browser.headers["X-CSRF-Token"] = browser.get("/api/auth/csrf").json()["csrf_token"]
        yield browser


ADMIN_ENDPOINTS = [
    ("GET", "/api/equipment"),
    ("GET", "/api/equipment/1"),
    ("GET", "/api/equipment/1/availability"),
    ("POST", "/api/equipment"),
    ("PUT", "/api/equipment/1"),
    ("PATCH", "/api/equipment/1"),
    ("GET", "/api/reservations"),
    ("GET", "/api/reservations/1"),
    ("POST", "/api/reservations"),
    ("POST", "/api/reservations/1/cancel"),
    ("GET", "/api/incidents"),
    ("GET", "/api/incidents/1"),
    ("POST", "/api/incidents"),
    ("PATCH", "/api/incidents/1/status"),
    ("PATCH", "/api/incidents/1"),
    ("POST", "/api/imports"),
    ("GET", "/api/imports/example"),
    ("GET", "/api/docs"),
    ("GET", "/api/docs/oauth2-redirect"),
    ("GET", "/api/redoc"),
    ("GET", "/api/openapi.json"),
]


@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
def test_customer_cannot_use_existing_management_endpoints(
    customer: TestClient, method: str, path: str
) -> None:
    # Invalid/missing bodies must not bypass the role check or expose validation details.
    response = customer.request(method, path)
    assert response.status_code == 403
    assert set(response.json()) == {"detail"}


@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
def test_existing_management_endpoints_require_a_session(
    app: FastAPI, method: str, path: str
) -> None:
    with TestClient(app) as anonymous:
        response = anonymous.request(method, path)
        assert response.status_code == 401
        assert set(response.json()) == {"detail"}


def test_customer_import_is_denied_before_consuming_multipart(customer: TestClient) -> None:
    consumed = False

    def upload() -> Iterator[bytes]:
        nonlocal consumed
        consumed = True
        yield b"This multipart body must not be read by a customer"

    request = customer.build_request(
        "POST",
        "/api/imports",
        content=upload(),
        headers={"Content-Type": "multipart/form-data; boundary=missing"},
    )
    assert customer.send(request).status_code == 403
    assert consumed is False


def create_private_history(
    admin: TestClient, equipment_payload: dict[str, object], email: str = CUSTOMER_EMAIL
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    equipment_response = admin.post("/api/equipment", json=equipment_payload)
    assert equipment_response.status_code == 201
    equipment = equipment_response.json()
    reservation_response = admin.post(
        "/api/reservations",
        json={
            "equipment_id": equipment["id"],
            "customer_name": "Nombre privado",
            "customer_email": email,
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
            "external_reference": "PRIVATE-REFERENCE",
        },
    )
    assert reservation_response.status_code == 201
    incident_response = admin.post(
        "/api/incidents",
        json={
            "equipment_id": equipment["id"],
            "title": "Informe privado",
            "description": "Descripción de uso privada",
            "blocking": False,
        },
    )
    assert incident_response.status_code == 201
    return equipment, reservation_response.json(), incident_response.json()


def test_catalog_and_date_availability_are_public_without_private_reservation_ids(
    app: FastAPI, client: TestClient, equipment_payload: dict[str, object]
) -> None:
    equipment, reservation, _incident = create_private_history(client, equipment_payload)
    path = f"/api/public/equipment/{equipment['id']}/availability"
    dates = {"start_date": "2026-11-10", "end_date": "2026-11-12"}
    administrative = client.get(f"/api/equipment/{equipment['id']}/availability", params=dates)
    assert administrative.status_code == 200
    assert administrative.json()["conflicting_reservation_ids"] == [reservation["id"]]

    with TestClient(app) as anonymous:
        catalog = anonymous.get("/api/public/equipment")
        detail = anonymous.get(f"/api/public/equipment/{equipment['id']}")
        availability = anonymous.get(path, params=dates)
        assert catalog.status_code == detail.status_code == availability.status_code == 200
        result = availability.json()
        assert result["available"] is False
        assert result["status"] == "unavailable"
        assert "reason" not in result
        assert result.get("conflicting_reservation_ids", []) == []
        for private_value in ["Nombre privado", CUSTOMER_EMAIL, "PRIVATE-REFERENCE"]:
            assert private_value not in catalog.text + detail.text + availability.text
        for private_path in [
            f"/api/reservations/{reservation['id']}",
            "/api/reservations/999999",
            "/api/incidents/999999",
        ]:
            assert anonymous.get(private_path).status_code == 401


def test_customer_cannot_read_unowned_history_even_when_its_email_matches(
    app: FastAPI,
    client: TestClient,
    customer: TestClient,
    equipment_payload: dict[str, object],
) -> None:
    _equipment, reservation, incident = create_private_history(client, equipment_payload)
    reservation_path = f"/api/reservations/{reservation['id']}"
    incident_path = f"/api/incidents/{incident['id']}"
    assert client.get(reservation_path).status_code == 200
    assert client.get(incident_path).status_code == 200
    assert customer.get(f"/api/me/reservations/{reservation['id']}").status_code == 404
    assert customer.get(f"/api/me/incidents/{incident['id']}").status_code == 404
    assert customer.get("/api/me/reservations/999999").status_code == 404
    assert customer.get("/api/me/incidents/999999").status_code == 404

    # Neither creation by an administrator nor a matching contact email confers ownership.
    with app.state.session_factory() as database_session:
        record = database_session.get(Reservation, reservation["id"])
        assert record is not None
        assert record.customer_user_id is None


def test_detail_permissions_follow_persisted_ownership_without_exposing_other_reservations(
    app: FastAPI,
    client: TestClient,
    customer: TestClient,
    equipment_payload: dict[str, object],
) -> None:
    from rentalab.auth.models import User

    equipment, reservation, incident = create_private_history(client, equipment_payload)
    with app.state.session_factory.begin() as database_session:
        user = database_session.scalar(select(User).where(User.email == CUSTOMER_EMAIL))
        assert user is not None
        record = database_session.get(Reservation, reservation["id"])
        report = database_session.get(Incident, incident["id"])
        assert record is not None and report is not None
        record.customer_user_id = user.id
        report.author_user_id = user.id
        report.reservation_id = record.id

    reservation_path = f"/api/me/reservations/{reservation['id']}"
    incident_path = f"/api/me/incidents/{incident['id']}"
    assert customer.get(reservation_path).status_code == 200
    # There is another unowned booking on the same unit, whose id stays private.
    other = client.post(
        "/api/reservations",
        json={
            "equipment_id": equipment["id"],
            "customer_name": "Otro cliente",
            "customer_email": "other@example.test",
            "start_date": "2026-12-10",
            "end_date": "2026-12-12",
        },
    )
    assert other.status_code == 201
    own_report = customer.get(incident_path)
    assert own_report.status_code == 200
    assert other.json()["id"] not in own_report.json().get("confirmed_reservation_ids", [])
    assert customer.get(f"/api/me/reservations/{other.json()['id']}").status_code == 404

    with app.state.session_factory.begin() as database_session:
        record = database_session.get(Reservation, reservation["id"])
        report = database_session.get(Incident, incident["id"])
        assert record is not None and report is not None
        record.customer_user_id = None
        report.author_user_id = None
    assert customer.get(reservation_path).status_code == 404
    assert customer.get(incident_path).status_code == 404


def test_customer_availability_hides_conflicting_reservation_ids(
    client: TestClient, customer: TestClient, equipment_payload: dict[str, object]
) -> None:
    equipment, _reservation, _incident = create_private_history(client, equipment_payload)
    response = customer.get(
        f"/api/public/equipment/{equipment['id']}/availability",
        params={"start_date": "2026-11-10", "end_date": "2026-11-12"},
    )
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json().get("conflicting_reservation_ids", []) == []


def test_register_does_not_claim_history_by_matching_email(
    app: FastAPI, client: TestClient, equipment_payload: dict[str, object]
) -> None:
    _equipment, reservation, _incident = create_private_history(client, equipment_payload)
    with TestClient(app) as browser:
        user = register_customer(browser)
        assert isinstance(user["id"], int)

    with app.state.session_factory() as database_session:
        record = database_session.get(Reservation, reservation["id"])
        assert record is not None
        assert record.customer_email == CUSTOMER_EMAIL
        assert record.customer_user_id is None


def test_live_database_role_controls_admin_access_and_incident_author_is_recorded(
    app: FastAPI,
    client: TestClient,
    customer: TestClient,
    equipment_payload: dict[str, object],
) -> None:
    from rentalab.auth.models import User

    equipment_response = client.post("/api/equipment", json=equipment_payload)
    assert equipment_response.status_code == 201
    equipment_id = equipment_response.json()["id"]
    with app.state.session_factory.begin() as database_session:
        user = database_session.scalar(select(User).where(User.email == CUSTOMER_EMAIL))
        assert user is not None
        user_id = user.id
        user.role = "admin"

    # The same existing cookie must use the current DB role on every request.
    assert customer.get("/api/reservations").status_code == 200
    report_response = customer.post(
        "/api/incidents", json={"equipment_id": equipment_id, "title": "Informe del administrador"}
    )
    assert report_response.status_code == 201
    with app.state.session_factory.begin() as database_session:
        report = database_session.get(Incident, report_response.json()["id"])
        assert report is not None
        assert report.author_user_id == user_id
        user = database_session.get(User, user_id)
        assert user is not None
        user.role = "customer"

    assert customer.get("/api/reservations").status_code == 403
    assert customer.post("/api/incidents", json={}).status_code == 403
    # An administrative report has no customer reservation; demotion grants no access.
    assert customer.get(f"/api/incidents/{report_response.json()['id']}").status_code == 403
    assert customer.get(f"/api/me/incidents/{report_response.json()['id']}").status_code == 404


def test_csv_does_not_assign_an_owner_from_an_existing_users_email(
    app: FastAPI,
    client: TestClient,
    customer: TestClient,
    equipment_payload: dict[str, object],
) -> None:
    equipment_response = client.post("/api/equipment", json=equipment_payload)
    assert equipment_response.status_code == 201
    content = (
        "external_reference,customer_name,customer_email,equipment_code,starts_on,ends_on\n"
        f"CSV-UNKNOWN-OWNER,Cliente importado,{CUSTOMER_EMAIL},CAM-001,2026-11-10,2026-11-12\n"
    ).encode()
    response = client.post("/api/imports", files={"file": ("orders.csv", content, "text/csv")})
    assert response.status_code == 200
    assert response.json()["totals"]["accepted"] == 1
    reservation_id = response.json()["rows"][0]["reservation"]["id"]
    with app.state.session_factory() as database_session:
        record = database_session.get(Reservation, reservation_id)
        assert record is not None
        assert record.customer_email == CUSTOMER_EMAIL
        assert record.customer_user_id is None
    assert customer.get(f"/api/me/reservations/{reservation_id}").status_code == 404


@pytest.mark.parametrize("email", ["de\u0301mo@example.test", "demo@ＥＸＡＭＰＬＥ.test"])
def test_login_accepts_the_same_email_spelling_accepted_during_registration(
    app: FastAPI, email: str
) -> None:
    with TestClient(app) as browser:
        user = register_customer(browser, email)
        token = browser.get("/api/auth/csrf").json()["csrf_token"]
        response = browser.post(
            "/api/auth/login",
            json={"username": email, "password": CUSTOMER_PASSWORD},
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 200
        assert response.json()["role"] == "customer"
        assert response.json()["user"]["id"] == user["id"]
