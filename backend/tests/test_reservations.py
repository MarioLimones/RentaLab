from typing import Any

import pytest
from conftest import authenticate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from rentalab.config import Settings
from rentalab.main import create_app


@pytest.fixture
def reservation_payload(
    client: TestClient, equipment_payload: dict[str, object]
) -> dict[str, object]:
    equipment = client.post("/api/equipment", json=equipment_payload)
    assert equipment.status_code == 201
    return {
        "equipment_id": equipment.json()["id"],
        "customer_name": "Cliente ficticio",
        "customer_email": "cliente@example.test",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
    }


def create_reservation(
    client: TestClient, payload: dict[str, object], **changes: object
) -> dict[str, Any]:
    response = client.post("/api/reservations", json={**payload, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_normalizes_returns_and_retrieves_a_confirmed_reservation(
    client: TestClient, reservation_payload: dict[str, object]
) -> None:
    payload = {
        **reservation_payload,
        "customer_name": "  Cliente ficticio  ",
        "customer_email": "  cliente@example.test  ",
        "external_reference": "  ORDER-001  ",
    }
    response = client.post("/api/reservations", json=payload)
    assert response.status_code == 201
    reservation = response.json()
    assert isinstance(reservation["id"], int)
    assert reservation == {
        **reservation_payload,
        "id": reservation["id"],
        "external_reference": "ORDER-001",
        "status": "confirmed",
        "customer_user_id": None,
        "origin": "admin",
    }
    assert response.headers["location"] == f"/api/reservations/{reservation['id']}"
    assert client.get(response.headers["location"]).json() == reservation
    assert client.get("/api/reservations").json() == [reservation]


def test_reference_is_optional_and_multiple_null_references_are_allowed(
    client: TestClient, reservation_payload: dict[str, object]
) -> None:
    first = create_reservation(client, reservation_payload)
    second = create_reservation(
        client,
        reservation_payload,
        start_date="2026-11-12",
        end_date="2026-11-13",
        external_reference=None,
    )
    assert first["external_reference"] is None
    assert second["external_reference"] is None


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [
        ("2026-11-09", "2026-11-11"),
        ("2026-11-11", "2026-11-13"),
        ("2026-11-10", "2026-11-12"),
        ("2026-11-09", "2026-11-13"),
        ("2026-11-10", "2026-11-11"),
        ("2026-11-11", "2026-11-12"),
    ],
)
def test_partial_total_and_contained_overlaps_are_conflicts(
    client: TestClient,
    reservation_payload: dict[str, object],
    start_date: str,
    end_date: str,
) -> None:
    original = create_reservation(client, reservation_payload)
    response = client.post(
        "/api/reservations",
        json={**reservation_payload, "start_date": start_date, "end_date": end_date},
    )
    assert response.status_code == 409
    assert isinstance(response.json()["detail"], str)
    assert client.get("/api/reservations").json() == [original]
    availability = client.get(
        f"/api/equipment/{reservation_payload['equipment_id']}/availability",
        params={"start_date": start_date, "end_date": end_date},
    )
    assert availability.status_code == 200
    assert availability.json() == {
        "equipment_id": reservation_payload["equipment_id"],
        "start_date": start_date,
        "end_date": end_date,
        "available": False,
        "reason": "reservation_overlap",
        "conflicting_reservation_ids": [original["id"]],
    }


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [
        ("2026-11-08", "2026-11-10"),
        ("2026-11-12", "2026-11-14"),
        ("2026-11-01", "2026-11-03"),
        ("2026-11-20", "2026-11-21"),
    ],
)
def test_adjacent_and_separate_ranges_are_available_and_can_be_reserved(
    client: TestClient,
    reservation_payload: dict[str, object],
    start_date: str,
    end_date: str,
) -> None:
    create_reservation(client, reservation_payload)
    response = client.get(
        f"/api/equipment/{reservation_payload['equipment_id']}/availability",
        params={"start_date": start_date, "end_date": end_date},
    )
    assert response.status_code == 200
    assert response.json() == {
        "equipment_id": reservation_payload["equipment_id"],
        "start_date": start_date,
        "end_date": end_date,
        "available": True,
        "reason": None,
        "conflicting_reservation_ids": [],
    }
    create_reservation(client, reservation_payload, start_date=start_date, end_date=end_date)


def test_the_same_dates_can_be_reserved_for_different_physical_units(
    client: TestClient,
    reservation_payload: dict[str, object],
    equipment_payload: dict[str, object],
) -> None:
    first = create_reservation(client, reservation_payload)
    second_equipment = client.post(
        "/api/equipment", json={**equipment_payload, "code": "CAM-002"}
    ).json()
    second = create_reservation(client, reservation_payload, equipment_id=second_equipment["id"])
    assert first["equipment_id"] != second["equipment_id"]
    assert len(client.get("/api/reservations").json()) == 2


def test_cancellation_preserves_history_is_idempotent_and_unblocks_the_range(
    client: TestClient, reservation_payload: dict[str, object]
) -> None:
    original = create_reservation(client, reservation_payload, external_reference="ORDER-1")
    url = f"/api/reservations/{original['id']}"
    cancelled = client.post(f"{url}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json() == {**original, "status": "cancelled"}
    assert client.post(f"{url}/cancel").json() == cancelled.json()
    assert client.get(url).json() == cancelled.json()
    availability = client.get(
        f"/api/equipment/{reservation_payload['equipment_id']}/availability",
        params={"start_date": "2026-11-10", "end_date": "2026-11-12"},
    )
    assert availability.json()["available"] is True
    assert availability.json()["conflicting_reservation_ids"] == []
    replacement = create_reservation(client, reservation_payload)
    assert replacement["id"] != original["id"]
    assert len(client.get("/api/reservations").json()) == 2


def test_inactive_equipment_is_unavailable_and_cannot_receive_new_reservations(
    client: TestClient, reservation_payload: dict[str, object]
) -> None:
    equipment_id = reservation_payload["equipment_id"]
    assert client.patch(f"/api/equipment/{equipment_id}", json={"active": False}).status_code == 200
    response = client.get(
        f"/api/equipment/{equipment_id}/availability",
        params={"start_date": "2026-11-10", "end_date": "2026-11-12"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "equipment_id": equipment_id,
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
        "available": False,
        "reason": "equipment_inactive",
        "conflicting_reservation_ids": [],
    }
    assert client.post("/api/reservations", json=reservation_payload).status_code == 409
    assert client.get("/api/reservations").json() == []


def test_deactivation_does_not_erase_reservations_or_prevent_cancellation(
    client: TestClient, reservation_payload: dict[str, object]
) -> None:
    original = create_reservation(client, reservation_payload)
    client.patch(f"/api/equipment/{reservation_payload['equipment_id']}", json={"active": False})
    assert client.get(f"/api/reservations/{original['id']}").json() == original
    assert client.post(f"/api/reservations/{original['id']}/cancel").json()["status"] == "cancelled"


def test_external_reference_is_trimmed_unique_and_remains_reserved_after_cancellation(
    client: TestClient, reservation_payload: dict[str, object]
) -> None:
    original = create_reservation(client, reservation_payload, external_reference=" ORDER-1 ")
    client.post(f"/api/reservations/{original['id']}/cancel")
    response = client.post(
        "/api/reservations", json={**reservation_payload, "external_reference": "ORDER-1"}
    )
    assert response.status_code == 409
    assert len(client.get("/api/reservations").json()) == 1
    different_case = create_reservation(client, reservation_payload, external_reference="order-1")
    assert different_case["external_reference"] == "order-1"


def test_list_filters_and_orders_reservations_by_start_then_id(
    client: TestClient,
    reservation_payload: dict[str, object],
    equipment_payload: dict[str, object],
) -> None:
    assert client.get("/api/reservations").json() == []
    late = create_reservation(
        client, reservation_payload, start_date="2026-11-20", end_date="2026-11-22"
    )
    second_equipment = client.post(
        "/api/equipment", json={**equipment_payload, "code": "MIC-002"}
    ).json()
    early = create_reservation(client, reservation_payload)
    same_start = create_reservation(
        client, reservation_payload, equipment_id=second_equipment["id"]
    )
    client.post(f"/api/reservations/{same_start['id']}/cancel")
    cancelled = {**same_start, "status": "cancelled"}
    assert client.get("/api/reservations").json() == [early, cancelled, late]
    assert client.get("/api/reservations", params={"status": "confirmed"}).json() == [
        early,
        late,
    ]
    assert client.get("/api/reservations", params={"status": "cancelled"}).json() == [cancelled]
    assert client.get(
        "/api/reservations", params={"equipment_id": second_equipment["id"]}
    ).json() == [cancelled]
    assert (
        client.get(
            "/api/reservations",
            params={"equipment_id": reservation_payload["equipment_id"], "status": "cancelled"},
        ).json()
        == []
    )
    assert client.get(
        "/api/reservations", params={"start_date": "2026-11-11", "end_date": "2026-11-20"}
    ).json() == [early, cancelled]
    assert (
        client.get(
            "/api/reservations", params={"start_date": "2026-11-12", "end_date": "2026-11-20"}
        ).json()
        == []
    )


def test_availability_reports_all_overlaps_without_exposing_customer_data(
    client: TestClient, reservation_payload: dict[str, object]
) -> None:
    first = create_reservation(client, reservation_payload)
    second = create_reservation(
        client, reservation_payload, start_date="2026-11-12", end_date="2026-11-14"
    )
    response = client.get(
        f"/api/equipment/{reservation_payload['equipment_id']}/availability",
        params={"start_date": "2026-11-09", "end_date": "2026-11-15"},
    )
    assert response.status_code == 200
    assert response.json()["conflicting_reservation_ids"] == [first["id"], second["id"]]
    assert "customer_name" not in response.text
    assert "customer_email" not in response.text


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("get", "/api/reservations/99999"),
        ("post", "/api/reservations/99999/cancel"),
        ("get", "/api/reservations?equipment_id=99999"),
        (
            "get",
            "/api/equipment/99999/availability?start_date=2026-11-10&end_date=2026-11-12",
        ),
    ],
)
def test_missing_resources_are_404(client: TestClient, method: str, url: str) -> None:
    response = client.request(method, url)
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)


def test_reserving_missing_equipment_is_404(
    client: TestClient, reservation_payload: dict[str, object]
) -> None:
    response = client.post("/api/reservations", json={**reservation_payload, "equipment_id": 99999})
    assert response.status_code == 404
    assert client.get("/api/reservations").json() == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("equipment_id", 0),
        ("equipment_id", -1),
        ("equipment_id", True),
        ("equipment_id", "1"),
        ("equipment_id", None),
        ("equipment_id", 2**63),
        ("customer_name", ""),
        ("customer_name", "   "),
        ("customer_name", "X" * 121),
        ("customer_name", None),
        ("customer_name", 123),
        ("customer_name", "\x00Cliente"),
        ("customer_name", "Cliente\x00ficticio"),
        ("customer_email", ""),
        ("customer_email", "no-email"),
        ("customer_email", "no-at.example.test"),
        ("customer_email", "@example.test"),
        ("customer_email", "cliente@"),
        ("customer_email", "cli ente@example.test"),
        ("customer_email", "cliente@@example.test"),
        ("customer_email", "X" * 255),
        ("customer_email", None),
        ("start_date", "2026-11-12"),
        ("start_date", "2026-11-13"),
        ("start_date", "2026-02-30"),
        ("start_date", "2026-1-01"),
        ("start_date", "10/11/2026"),
        ("start_date", "2026-11-10T00:00:00"),
        ("start_date", " 2026-11-10 "),
        ("start_date", 1794268800),
        ("start_date", None),
        ("end_date", "2026-11-10"),
        ("end_date", "2026-11-09"),
        ("end_date", "2026-13-01"),
        ("end_date", "2026-11-12T00:00:00Z"),
        ("end_date", 1794441600),
        ("end_date", None),
        ("external_reference", ""),
        ("external_reference", "   "),
        ("external_reference", "X" * 121),
        ("external_reference", 42),
        ("external_reference", "\x00ORDER-1"),
        ("external_reference", "ORDER-1\x00ficticio"),
        ("status", "confirmed"),
        ("status", "cancelled"),
        ("unknown", "unexpected"),
    ],
)
def test_invalid_reservations_are_422_without_writing(
    client: TestClient, reservation_payload: dict[str, object], field: str, value: object
) -> None:
    response = client.post("/api/reservations", json={**reservation_payload, field: value})
    assert response.status_code == 422
    assert client.get("/api/reservations").json() == []


@pytest.mark.parametrize(
    "field", ["equipment_id", "customer_name", "customer_email", "start_date", "end_date"]
)
def test_creation_requires_all_mandatory_fields(
    client: TestClient, reservation_payload: dict[str, object], field: str
) -> None:
    del reservation_payload[field]
    assert client.post("/api/reservations", json=reservation_payload).status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"start_date": "2026-11-10"},
        {"end_date": "2026-11-12"},
        {"start_date": "2026-11-10", "end_date": "2026-11-10"},
        {"start_date": "2026-11-12", "end_date": "2026-11-10"},
        {"start_date": "2026-02-30", "end_date": "2026-11-12"},
        {"start_date": "2026-11-10T00:00:00", "end_date": "2026-11-12"},
        {"start_date": "2026-11-10", "end_date": "2026-11-12T00:00:00Z"},
        {"start_date": "1794268800", "end_date": "2026-11-12"},
    ],
)
def test_availability_requires_a_valid_complete_iso_date_range(
    client: TestClient, reservation_payload: dict[str, object], params: dict[str, str]
) -> None:
    response = client.get(
        f"/api/equipment/{reservation_payload['equipment_id']}/availability", params=params
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"equipment_id": "0"},
        {"equipment_id": "-1"},
        {"equipment_id": "invalid"},
        {"equipment_id": str(2**63)},
        {"status": "pending"},
        {"start_date": "2026-11-10"},
        {"end_date": "2026-11-12"},
        {"start_date": "2026-11-10", "end_date": "2026-11-10"},
        {"start_date": "2026-11-12", "end_date": "2026-11-10"},
        {"start_date": "2026-11-10T00:00:00", "end_date": "2026-11-12"},
    ],
)
def test_invalid_list_filters_are_422(client: TestClient, params: dict[str, str]) -> None:
    assert client.get("/api/reservations", params=params).status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", f"/api/reservations/{2**63}"),
        ("post", f"/api/reservations/{2**63}/cancel"),
        ("get", f"/api/equipment/{2**63}"),
        ("get", f"/api/equipment/{2**63}/availability?start_date=2026-11-10&end_date=2026-11-12"),
    ],
)
def test_ids_outside_sqlite_integer_range_are_422(
    client: TestClient, method: str, path: str
) -> None:
    assert client.request(method, path).status_code == 422


def test_reservations_and_cancellation_persist_when_application_is_recreated(
    client: TestClient, reservation_payload: dict[str, object], settings: Settings
) -> None:
    original = create_reservation(client, reservation_payload)
    cancelled = client.post(f"/api/reservations/{original['id']}/cancel").json()
    application = create_app(settings)
    try:
        with TestClient(application) as recreated_client:
            authenticate(recreated_client)
            assert recreated_client.get("/api/reservations").json() == [cancelled]
            assert recreated_client.get(f"/api/reservations/{original['id']}").json() == cancelled
            create_reservation(recreated_client, reservation_payload)
    finally:
        application.state.engine.dispose()


@pytest.mark.parametrize(
    "changes",
    [
        {"external_reference": "ORDER-DB"},
        {"equipment_id": 99999, "external_reference": None},
        {"end_date": "2026-11-10", "external_reference": None},
        {"end_date": "2026-11-09", "external_reference": None},
        {"status": "pending", "external_reference": None},
    ],
)
def test_sqlite_enforces_external_reference_date_status_and_foreign_key_constraints(
    app: FastAPI,
    client: TestClient,
    reservation_payload: dict[str, object],
    changes: dict[str, object],
) -> None:
    create_reservation(client, reservation_payload, external_reference="ORDER-DB")
    parameters = {
        **reservation_payload,
        "status": "confirmed",
        "external_reference": None,
        **changes,
    }
    with pytest.raises(IntegrityError), app.state.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO reservations (equipment_id, customer_name, customer_email, "
                "start_date, end_date, status, external_reference) "
                "VALUES (:equipment_id, :customer_name, :customer_email, "
                ":start_date, :end_date, :status, :external_reference)"
            ),
            parameters,
        )
