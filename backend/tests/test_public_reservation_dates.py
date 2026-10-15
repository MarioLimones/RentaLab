"""On-demand public reservation dates keep one range per active booking and no identity."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from test_public_calendar import reserve
from test_public_catalogue import create_equipment
from test_public_catalogue import visitor as visitor
from test_public_reservation_counts import business_today as business_today


@pytest.mark.usefixtures("business_today")
def test_public_dates_keep_duplicates_overlap_and_original_dates_in_stable_order(
    app: FastAPI, client: TestClient, visitor: TestClient
) -> None:
    units = [create_equipment(client, code=f"MODEL-{index}") for index in range(3)]
    reserve(client, units[0]["id"], "2030-12-10", "2030-12-12")
    reserve(client, units[0]["id"], "2030-11-14", "2030-11-18")
    reserve(client, units[1]["id"], "2030-11-14", "2030-11-18")
    reserve(client, units[2]["id"], "2030-11-14", "2030-11-16")
    reserve(client, units[2]["id"], "2030-11-16", "2030-11-19")
    expected = {
        "equipment_id": units[0]["id"],
        "reservations": [
            {"start_date": "2030-11-14", "end_date": "2030-11-16"},
            {"start_date": "2030-11-14", "end_date": "2030-11-18"},
            {"start_date": "2030-11-14", "end_date": "2030-11-18"},
            {"start_date": "2030-11-16", "end_date": "2030-11-19"},
            {"start_date": "2030-12-10", "end_date": "2030-12-12"},
        ],
    }
    queries: list[str] = []

    def record_query(_connection: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        if "reservations" in statement:
            queries.append(statement)

    event.listen(app.state.engine, "before_cursor_execute", record_query)
    try:
        response = visitor.get(f"/api/public/equipment/{units[1]['id']}/reservations")
    finally:
        event.remove(app.state.engine, "before_cursor_execute", record_query)
    assert response.status_code == 200
    assert response.json() == expected
    assert response.headers["cache-control"] == "no-store"
    assert client.get(f"/api/public/equipment/{units[0]['id']}/reservations").json() == expected
    assert visitor.get("/api/public/equipment").json()[0]["active_reservations_count"] == 5
    assert len(queries) == 1
    selected_columns = queries[0].split("FROM")[0].strip()
    assert selected_columns == "SELECT reservations.start_date, reservations.end_date"
    assert "customer" not in queries[0]
    assert "external_reference" not in queries[0]
    assert "ORDER BY reservations.start_date, reservations.end_date, reservations.id" in queries[0]
    assert "PRIVATE-" not in response.text
    assert "private-calendar@example.test" not in response.text


def test_public_dates_are_empty_without_bookings_and_hide_inactive_or_missing_equipment(
    client: TestClient, visitor: TestClient
) -> None:
    equipment = create_equipment(client)
    url = f"/api/public/equipment/{equipment['id']}/reservations"
    response = visitor.get(url)
    assert response.status_code == 200
    assert response.json() == {"equipment_id": equipment["id"], "reservations": []}
    deactivated = client.patch(f"/api/equipment/{equipment['id']}", json={"active": False})
    assert deactivated.status_code == 200
    inactive = visitor.get(url)
    missing = visitor.get("/api/public/equipment/999999/reservations")
    assert inactive.status_code == missing.status_code == 404
    assert inactive.json() == missing.json() == {"detail": "El equipo no existe"}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_public_reservation_dates_reject_writes_and_preserve_history(
    client: TestClient, visitor: TestClient, method: str
) -> None:
    equipment = create_equipment(client)
    reserve(client, equipment["id"], "2030-11-18", "2030-11-20")
    before = client.get("/api/reservations").json()
    path = f"/api/public/equipment/{equipment['id']}/reservations"
    assert visitor.request(method, path, json={"status": "cancelled"}).status_code == 401
    assert client.request(method, path, json={"status": "cancelled"}).status_code == 405
    assert client.get("/api/reservations").json() == before


@pytest.mark.parametrize("parameters", [{"start_date": "2030-11-18"}, {"status": "cancelled"}])
def test_public_reservation_dates_do_not_accept_filters(
    client: TestClient, visitor: TestClient, parameters: dict[str, str]
) -> None:
    equipment = create_equipment(client)
    response = visitor.get(
        f"/api/public/equipment/{equipment['id']}/reservations", params=parameters
    )
    assert response.status_code == 422


def test_public_reservation_dates_openapi_exposes_only_dates_without_authentication(
    client: TestClient,
) -> None:
    schema = client.get("/api/openapi.json").json()
    operation = schema["paths"]["/api/public/equipment/{equipment_id}/reservations"]["get"]
    assert operation["security"] == []
    assert {parameter["in"] for parameter in operation["parameters"]} == {"path"}
    assert "503" in operation["responses"]
    model = schema["components"]["schemas"]["PublicReservationsRead"]
    assert set(model["properties"]) == {"equipment_id", "reservations"}
    item_ref = model["properties"]["reservations"]["items"]["$ref"].split("/")[-1]
    assert set(schema["components"]["schemas"][item_ref]["properties"]) == {
        "start_date",
        "end_date",
    }
