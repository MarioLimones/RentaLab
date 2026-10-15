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
def incident_payload(client: TestClient, equipment_payload: dict[str, object]) -> dict[str, object]:
    equipment = client.post("/api/equipment", json=equipment_payload)
    assert equipment.status_code == 201
    return {"equipment_id": equipment.json()["id"], "title": "Conector de audio defectuoso"}


def create_incident(
    client: TestClient, payload: dict[str, object], **changes: object
) -> dict[str, Any]:
    response = client.post("/api/incidents", json={**payload, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def book_equipment(client: TestClient, equipment_id: object, **changes: object) -> dict[str, Any]:
    response = client.post(
        "/api/reservations",
        json={
            "equipment_id": equipment_id,
            "customer_name": "Cliente ficticio",
            "customer_email": "incidents@example.test",
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
            **changes,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def availability(client: TestClient, equipment_id: object) -> dict[str, Any]:
    response = client.get(
        f"/api/equipment/{equipment_id}/availability",
        params={"start_date": "2026-11-10", "end_date": "2026-11-12"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_create_normalizes_defaults_and_retrieves_an_open_incident(
    client: TestClient, incident_payload: dict[str, object]
) -> None:
    response = client.post(
        "/api/incidents", json={**incident_payload, "title": "  Conector de audio defectuoso  "}
    )
    assert response.status_code == 201
    incident = response.json()
    assert isinstance(incident["id"], int)
    assert incident == {
        **incident_payload,
        "id": incident["id"],
        "reservation_id": None,
        "author_user_id": None,
        "description": "",
        "priority": "medium",
        "blocking": False,
        "status": "open",
        "resolution": "",
        "public_response": "",
        "internal_notes": "",
        "confirmed_reservation_ids": [],
        "warning": None,
    }
    assert response.headers["location"] == f"/api/incidents/{incident['id']}"
    assert client.get(response.headers["location"]).json() == incident
    assert client.get("/api/incidents").json() == [incident]


@pytest.mark.parametrize("priority", ["low", "medium", "high"])
@pytest.mark.parametrize("blocking", [False, True])
def test_create_accepts_each_priority_and_explicit_blocking_mode(
    client: TestClient, incident_payload: dict[str, object], priority: str, blocking: bool
) -> None:
    incident = create_incident(
        client,
        incident_payload,
        description="  Inspección técnica ficticia  ",
        priority=priority,
        blocking=blocking,
    )
    assert incident["description"] == "Inspección técnica ficticia"
    assert incident["priority"] == priority
    assert incident["blocking"] is blocking


def test_incidents_can_be_registered_for_an_inactive_unit(
    client: TestClient, incident_payload: dict[str, object]
) -> None:
    equipment_id = incident_payload["equipment_id"]
    client.patch(f"/api/equipment/{equipment_id}", json={"active": False})
    incident = create_incident(client, incident_payload, blocking=True)
    assert incident["equipment_id"] == equipment_id
    assert incident["status"] == "open"


@pytest.mark.parametrize("path", [["in_progress"], ["resolved"], ["in_progress", "resolved"]])
def test_allowed_transitions_preserve_the_incident_and_trim_resolution(
    client: TestClient, incident_payload: dict[str, object], path: list[str]
) -> None:
    original = create_incident(client, incident_payload, blocking=True, priority="high")
    current = original
    for status in path:
        body = {"status": status}
        if status == "resolved":
            body["resolution"] = "  Conector sustituido en taller ficticio  "
        response = client.patch(f"/api/incidents/{original['id']}/status", json=body)
        assert response.status_code == 200
        current = response.json()
        assert current == {
            **original,
            "status": status,
            "resolution": "Conector sustituido en taller ficticio" if status == "resolved" else "",
        }
    assert client.get(f"/api/incidents/{original['id']}").json() == current
    assert client.get("/api/incidents").json() == [current]


@pytest.mark.parametrize(
    ("initial", "target"),
    [
        ("open", "open"),
        ("in_progress", "in_progress"),
        ("in_progress", "open"),
        ("resolved", "resolved"),
        ("resolved", "open"),
        ("resolved", "in_progress"),
    ],
)
def test_repeated_backward_and_terminal_transitions_are_conflicts_without_changes(
    client: TestClient, incident_payload: dict[str, object], initial: str, target: str
) -> None:
    incident = create_incident(client, incident_payload)
    url = f"/api/incidents/{incident['id']}/status"
    if initial != "open":
        body = {"status": initial}
        if initial == "resolved":
            body["resolution"] = "Reparación original"
        response = client.patch(url, json=body)
        assert response.status_code == 200
        incident = response.json()
    body = {"status": target}
    if target == "resolved":
        body["resolution"] = "Intento de reemplazar el historial"
    response = client.patch(url, json=body)
    assert response.status_code == 409
    assert isinstance(response.json()["detail"], str)
    assert client.get(f"/api/incidents/{incident['id']}").json() == incident


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"status": "invalid"},
        {"status": None},
        {"status": "resolved"},
        {"status": "resolved", "resolution": None},
        {"status": "resolved", "resolution": ""},
        {"status": "resolved", "resolution": "   "},
        {"status": "resolved", "resolution": "X" * 2001},
        {"status": "resolved", "resolution": "Repair\x00bad"},
        {"status": "resolved", "resolution": 12},
        {"status": "in_progress", "resolution": ""},
        {"status": "in_progress", "resolution": "Premature repair"},
        {"status": "in_progress", "blocking": False},
        {"status": "in_progress", "unknown": True},
    ],
)
def test_invalid_status_changes_are_422_and_preserve_the_original(
    client: TestClient, incident_payload: dict[str, object], body: dict[str, object]
) -> None:
    incident = create_incident(client, incident_payload)
    response = client.patch(f"/api/incidents/{incident['id']}/status", json=body)
    assert response.status_code == 422
    assert client.get(f"/api/incidents/{incident['id']}").json() == incident


def test_null_resolution_is_allowed_for_the_in_progress_transition(
    client: TestClient, incident_payload: dict[str, object]
) -> None:
    incident = create_incident(client, incident_payload)
    response = client.patch(
        f"/api/incidents/{incident['id']}/status",
        json={"status": "in_progress", "resolution": None},
    )
    assert response.status_code == 200
    assert response.json()["resolution"] == ""


def test_blocking_incident_prevents_reservation_until_resolved(
    client: TestClient, incident_payload: dict[str, object]
) -> None:
    equipment_id = incident_payload["equipment_id"]
    incident = create_incident(client, incident_payload, blocking=True)
    expected = {
        "equipment_id": equipment_id,
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
        "available": False,
        "reason": "blocking_incident",
        "conflicting_reservation_ids": [],
    }
    assert availability(client, equipment_id) == expected
    booking = {
        "equipment_id": equipment_id,
        "customer_name": "Cliente ficticio",
        "customer_email": "blocked@example.test",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
    }
    assert client.post("/api/reservations", json=booking).status_code == 409
    assert client.get("/api/reservations").json() == []
    url = f"/api/incidents/{incident['id']}/status"
    assert client.patch(url, json={"status": "in_progress"}).status_code == 200
    assert availability(client, equipment_id) == expected
    assert client.post("/api/reservations", json=booking).status_code == 409
    assert (
        client.patch(url, json={"status": "resolved", "resolution": "Reparación"}).status_code
        == 200
    )
    assert availability(client, equipment_id) == {**expected, "available": True, "reason": None}
    assert client.post("/api/reservations", json=booking).status_code == 201
    assert client.get(f"/api/incidents/{incident['id']}").json()["status"] == "resolved"


def test_multiple_blocking_incidents_require_resolving_the_last_one(
    client: TestClient, incident_payload: dict[str, object]
) -> None:
    equipment_id = incident_payload["equipment_id"]
    first = create_incident(client, incident_payload, blocking=True)
    second = create_incident(client, incident_payload, blocking=True)
    create_incident(client, incident_payload, blocking=False)
    for incident in (first, second):
        response = client.patch(
            f"/api/incidents/{incident['id']}/status",
            json={"status": "resolved", "resolution": "Reparación ficticia"},
        )
        assert response.status_code == 200
        assert availability(client, equipment_id)["available"] is (incident == second)
    assert len(client.get("/api/incidents").json()) == 3
    book_equipment(client, equipment_id)


@pytest.mark.parametrize("status", ["open", "in_progress"])
def test_nonblocking_unresolved_incidents_do_not_block_reservations(
    client: TestClient, incident_payload: dict[str, object], status: str
) -> None:
    incident = create_incident(client, incident_payload, blocking=False)
    if status == "in_progress":
        assert (
            client.patch(
                f"/api/incidents/{incident['id']}/status", json={"status": status}
            ).status_code
            == 200
        )
    assert availability(client, incident_payload["equipment_id"])["available"] is True
    book_equipment(client, incident_payload["equipment_id"])


def test_unavailability_reason_precedence_and_reservations_are_preserved(
    client: TestClient, incident_payload: dict[str, object]
) -> None:
    equipment_id = incident_payload["equipment_id"]
    booking = book_equipment(client, equipment_id)
    incident = create_incident(client, incident_payload, blocking=True)
    assert availability(client, equipment_id)["reason"] == "blocking_incident"
    assert availability(client, equipment_id)["conflicting_reservation_ids"] == []
    client.patch(f"/api/equipment/{equipment_id}", json={"active": False})
    assert availability(client, equipment_id)["reason"] == "equipment_inactive"
    assert (
        client.patch(
            f"/api/incidents/{incident['id']}/status",
            json={"status": "resolved", "resolution": "Reparación"},
        ).status_code
        == 200
    )
    assert availability(client, equipment_id)["reason"] == "equipment_inactive"
    client.patch(f"/api/equipment/{equipment_id}", json={"active": True})
    assert availability(client, equipment_id)["reason"] == "reservation_overlap"
    assert availability(client, equipment_id)["conflicting_reservation_ids"] == [booking["id"]]
    assert client.get(f"/api/reservations/{booking['id']}").json() == booking


def test_blocking_incidents_only_affect_their_physical_unit(
    client: TestClient,
    incident_payload: dict[str, object],
    equipment_payload: dict[str, object],
) -> None:
    create_incident(client, incident_payload, blocking=True)
    other_equipment = client.post(
        "/api/equipment", json={**equipment_payload, "code": "OTHER-001"}
    ).json()
    assert availability(client, other_equipment["id"])["available"] is True
    book_equipment(client, other_equipment["id"])


@pytest.mark.parametrize("blocking", [False, True])
def test_incident_warns_about_all_confirmed_reservations_without_mutating_them(
    client: TestClient, incident_payload: dict[str, object], blocking: bool
) -> None:
    equipment_id = incident_payload["equipment_id"]
    old = book_equipment(
        client,
        equipment_id,
        start_date="2020-01-10",
        end_date="2020-01-12",
        external_reference="OLD",
    )
    future = book_equipment(
        client,
        equipment_id,
        start_date="2030-01-10",
        end_date="2030-01-12",
        external_reference="NEW",
    )
    cancelled = book_equipment(client, equipment_id)
    assert client.post(f"/api/reservations/{cancelled['id']}/cancel").status_code == 200
    before = client.get("/api/reservations").json()
    incident = create_incident(client, incident_payload, blocking=blocking)
    assert incident["confirmed_reservation_ids"] == [old["id"], future["id"]]
    assert isinstance(incident["warning"], str) and incident["warning"].strip()
    assert "customer_email" not in incident
    assert "customer_name" not in incident
    assert client.get("/api/reservations").json() == before
    assert client.get(f"/api/incidents/{incident['id']}").json() == incident
    assert client.get("/api/incidents").json() == [incident]
    assert (
        client.patch(
            f"/api/incidents/{incident['id']}/status",
            json={"status": "resolved", "resolution": "Reparación"},
        ).status_code
        == 200
    )
    assert client.get("/api/reservations").json() == before


def test_warning_is_derived_from_current_confirmed_reservations(
    client: TestClient, incident_payload: dict[str, object]
) -> None:
    incident = create_incident(client, incident_payload, blocking=False)
    assert incident["warning"] is None
    booking = book_equipment(client, incident_payload["equipment_id"])
    response = client.get(f"/api/incidents/{incident['id']}").json()
    assert response["confirmed_reservation_ids"] == [booking["id"]]
    assert isinstance(response["warning"], str)
    assert client.get("/api/incidents").json() == [response]
    client.post(f"/api/reservations/{booking['id']}/cancel")
    assert client.get(f"/api/incidents/{incident['id']}").json() == incident


def test_list_filters_are_combinable_and_ordered_by_id(
    client: TestClient,
    incident_payload: dict[str, object],
    equipment_payload: dict[str, object],
) -> None:
    assert client.get("/api/incidents").json() == []
    first = create_incident(client, incident_payload, blocking=True, priority="high")
    second = create_incident(client, incident_payload, blocking=False, priority="low")
    other_equipment = client.post(
        "/api/equipment", json={**equipment_payload, "code": "OTHER-001"}
    ).json()
    third = create_incident(
        client, incident_payload, equipment_id=other_equipment["id"], priority="high"
    )
    second = client.patch(
        f"/api/incidents/{second['id']}/status", json={"status": "in_progress"}
    ).json()
    third = client.patch(
        f"/api/incidents/{third['id']}/status",
        json={"status": "resolved", "resolution": "Reparación"},
    ).json()
    assert client.get("/api/incidents").json() == [first, second, third]
    for filters, expected in [
        ({"equipment_id": incident_payload["equipment_id"]}, [first, second]),
        ({"status": "open"}, [first]),
        ({"status": "in_progress"}, [second]),
        ({"status": "resolved"}, [third]),
        ({"priority": "high"}, [first, third]),
        ({"blocking": "true"}, [first]),
        ({"blocking": "false"}, [second, third]),
        (
            {
                "equipment_id": incident_payload["equipment_id"],
                "status": "open",
                "priority": "high",
                "blocking": "true",
            },
            [first],
        ),
        ({"status": "resolved", "blocking": "true"}, []),
    ]:
        assert client.get("/api/incidents", params=filters).json() == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("equipment_id", 0),
        ("equipment_id", -1),
        ("equipment_id", 2**63),
        ("equipment_id", True),
        ("equipment_id", "1"),
        ("equipment_id", 1.0),
        ("equipment_id", None),
        ("title", ""),
        ("title", "   "),
        ("title", "X" * 161),
        ("title", "Fault\x00bad"),
        ("title", 12),
        ("title", None),
        ("description", "X" * 2001),
        ("description", "Fault\x00bad"),
        ("description", None),
        ("priority", "critical"),
        ("priority", "HIGH"),
        ("priority", None),
        ("blocking", "false"),
        ("blocking", 0),
        ("blocking", 1),
        ("blocking", None),
        ("status", "open"),
        ("resolution", "Repaired"),
        ("confirmed_reservation_ids", []),
        ("unknown", True),
    ],
)
def test_invalid_incident_creation_is_422_without_writing(
    client: TestClient, incident_payload: dict[str, object], field: str, value: object
) -> None:
    response = client.post("/api/incidents", json={**incident_payload, field: value})
    assert response.status_code == 422
    assert client.get("/api/incidents").json() == []


@pytest.mark.parametrize("field", ["equipment_id", "title"])
def test_incident_creation_requires_mandatory_fields(
    client: TestClient, incident_payload: dict[str, object], field: str
) -> None:
    del incident_payload[field]
    assert client.post("/api/incidents", json=incident_payload).status_code == 422


@pytest.mark.parametrize(
    "filters",
    [
        {"equipment_id": "0"},
        {"equipment_id": "-1"},
        {"equipment_id": str(2**63)},
        {"equipment_id": "invalid"},
        {"status": "cancelled"},
        {"priority": "critical"},
        {"blocking": "perhaps"},
    ],
)
def test_invalid_list_filters_are_422(client: TestClient, filters: dict[str, str]) -> None:
    assert client.get("/api/incidents", params=filters).status_code == 422


def test_missing_incident_equipment_and_status_target_return_404(
    client: TestClient, incident_payload: dict[str, object]
) -> None:
    assert client.get("/api/incidents/99999").status_code == 404
    assert (
        client.patch("/api/incidents/99999/status", json={"status": "in_progress"}).status_code
        == 404
    )
    assert client.get("/api/incidents?equipment_id=99999").status_code == 404
    assert (
        client.post("/api/incidents", json={**incident_payload, "equipment_id": 99999}).status_code
        == 404
    )
    assert client.get("/api/incidents").json() == []


def test_resolved_incident_and_its_history_persist_across_application_recreation(
    client: TestClient, incident_payload: dict[str, object], settings: Settings
) -> None:
    incident = create_incident(client, incident_payload, blocking=True)
    resolved = client.patch(
        f"/api/incidents/{incident['id']}/status",
        json={"status": "resolved", "resolution": "Sustitución ficticia"},
    )
    assert resolved.status_code == 200
    application = create_app(settings)
    try:
        with TestClient(application) as recreated:
            authenticate(recreated)
            assert recreated.get("/api/incidents").json() == [resolved.json()]
            assert availability(recreated, incident_payload["equipment_id"])["available"] is True
    finally:
        application.state.engine.dispose()


@pytest.mark.parametrize(
    "changes",
    [
        {"equipment_id": 99999},
        {"status": "cancelled"},
        {"priority": "critical"},
        {"status": "resolved", "resolution": ""},
        {"status": "open", "resolution": "Repaired"},
    ],
)
def test_sqlite_enforces_incident_foreign_key_and_state_constraints(
    app: FastAPI, incident_payload: dict[str, object], changes: dict[str, object]
) -> None:
    parameters = {
        **incident_payload,
        "description": "",
        "priority": "medium",
        "blocking": False,
        "status": "open",
        "resolution": "",
        **changes,
    }
    with pytest.raises(IntegrityError), app.state.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO incidents (equipment_id, title, description, priority, blocking, "
                "status, resolution) VALUES (:equipment_id, :title, :description, :priority, "
                ":blocking, :status, :resolution)"
            ),
            parameters,
        )
