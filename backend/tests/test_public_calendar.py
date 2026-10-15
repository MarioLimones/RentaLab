from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_public_catalogue import create_equipment, report_problem

from rentalab.config import Settings
from rentalab.main import create_app

WINDOW = {"start_date": "2026-11-01", "end_date": "2026-12-01"}
CALENDAR_FIELDS = {
    "equipment_id",
    "start_date",
    "end_date",
    "occupied_ranges",
    "can_book",
    "unavailable_end_dates",
}


@pytest.fixture
def calendar_visitor(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as browser:
        yield browser


def reserve(admin: TestClient, equipment_id: int, start: str, end: str) -> dict:
    response = admin.post(
        "/api/reservations",
        json={
            "equipment_id": equipment_id,
            "start_date": start,
            "end_date": end,
            "customer_name": "PRIVATE-CALENDAR-NAME",
            "customer_email": "private-calendar@example.test",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_calendar_publishes_only_clipped_merged_confirmed_dates_and_cancellation_refresh(
    client: TestClient, calendar_visitor: TestClient
) -> None:
    equipment = create_equipment(client)
    other = create_equipment(client, code="OTHER-UNIT", name="Otro modelo")
    reserve(client, equipment["id"], "2026-10-30", "2026-11-03")
    reserve(client, equipment["id"], "2026-11-03", "2026-11-06")
    last = reserve(client, equipment["id"], "2026-11-10", "2026-12-03")
    reserve(client, other["id"], "2026-11-01", "2026-12-01")
    url = f"/api/public/equipment/{equipment['id']}/calendar"
    for browser in (client, calendar_visitor):
        response = browser.get(url, params=WINDOW)
        assert response.status_code == 200, response.text
        assert response.json() == {
            "equipment_id": equipment["id"],
            **WINDOW,
            "can_book": True,
            "unavailable_end_dates": [],
            "occupied_ranges": [
                {"start_date": "2026-11-01", "end_date": "2026-11-06"},
                {"start_date": "2026-11-10", "end_date": "2026-12-01"},
            ],
        }
        assert set(response.json()) == CALENDAR_FIELDS
        assert "PRIVATE-" not in response.text
        assert "private-calendar@example.test" not in response.text
        for period in response.json()["occupied_ranges"]:
            assert set(period) == {"start_date", "end_date"}
    consecutive = calendar_visitor.get(
        url, params={"start_date": "2026-11-06", "end_date": "2026-11-10"}
    )
    assert consecutive.json()["occupied_ranges"] == []
    assert client.post(f"/api/reservations/{last['id']}/cancel").status_code == 200
    refreshed = calendar_visitor.get(url, params=WINDOW)
    assert refreshed.json()["occupied_ranges"] == [
        {"start_date": "2026-11-01", "end_date": "2026-11-06"}
    ]


@pytest.mark.parametrize("blocking", [False, True])
@pytest.mark.parametrize("status", ["open", "in_progress", "resolved"])
def test_calendar_explains_generic_booking_block_without_incident_data(
    client: TestClient, calendar_visitor: TestClient, blocking: bool, status: str
) -> None:
    equipment = create_equipment(client)
    incident = report_problem(client, equipment["id"], blocking)
    if status != "open":
        body = {"status": status}
        if status == "resolved":
            body["resolution"] = "PRIVATE-RESOLUTION"
        assert client.patch(f"/api/incidents/{incident['id']}/status", json=body).status_code == 200
    response = calendar_visitor.get(
        f"/api/public/equipment/{equipment['id']}/calendar", params=WINDOW
    )
    assert response.status_code == 200, response.text
    assert response.json()["can_book"] is (not blocking or status == "resolved")
    assert response.json()["occupied_ranges"] == []
    assert set(response.json()) == CALENDAR_FIELDS
    assert "PRIVATE-" not in response.text


@pytest.mark.parametrize(
    "dates",
    [
        {},
        {"start_date": "2026-11-01"},
        {"end_date": "2026-12-01"},
        {"start_date": "2026-11-01", "end_date": "2026-11-01"},
        {"start_date": "2026-12-01", "end_date": "2026-11-01"},
        {"start_date": "2026-02-30", "end_date": "2026-12-01"},
        {"start_date": "2026-11-01T00:00:00", "end_date": "2026-12-01"},
        {"start_date": "2026-1-01", "end_date": "2026-12-01"},
        {"start_date": "2026-01-01", "end_date": "2027-01-03"},
        {**WINDOW, "customer_user_id": "1"},
        {**WINDOW, "booking_start": "2026-02-30"},
        {**WINDOW, "booking_start": "2026-11-01T00:00:00"},
        {**WINDOW, "booking_start": "2026-1-01"},
        {**WINDOW, "booking_start": "2025-11-29"},
    ],
)
def test_calendar_rejects_invalid_partial_unbounded_or_private_queries(
    client: TestClient, calendar_visitor: TestClient, dates: dict[str, str]
) -> None:
    equipment = create_equipment(client)
    response = calendar_visitor.get(
        f"/api/public/equipment/{equipment['id']}/calendar", params=dates
    )
    assert response.status_code == 422, response.text


def test_calendar_accepts_at_most_366_days_and_hides_inactive_units(
    client: TestClient, calendar_visitor: TestClient
) -> None:
    equipment = create_equipment(client)
    url = f"/api/public/equipment/{equipment['id']}/calendar"
    maximum = {"start_date": "2026-01-01", "end_date": "2027-01-02"}
    assert calendar_visitor.get(url, params=maximum).status_code == 200
    assert (
        client.patch(f"/api/equipment/{equipment['id']}", json={"active": False}).status_code == 200
    )
    inactive = calendar_visitor.get(url, params=WINDOW)
    missing = calendar_visitor.get("/api/public/equipment/999999/calendar", params=WINDOW)
    assert inactive.status_code == missing.status_code == 404
    assert inactive.json() == missing.json()


def test_calendar_persists_across_application_and_connection_pool_recreation(
    client: TestClient, settings: Settings
) -> None:
    equipment = create_equipment(client)
    reserve(client, equipment["id"], "2026-11-10", "2026-11-12")
    cancelled = reserve(client, equipment["id"], "2026-11-20", "2026-11-22")
    assert client.post(f"/api/reservations/{cancelled['id']}/cancel").status_code == 200
    url = f"/api/public/equipment/{equipment['id']}/calendar"
    before = client.get(url, params=WINDOW).json()
    recreated = create_app(settings)
    try:
        with TestClient(recreated) as visitor:
            after = visitor.get(url, params=WINDOW)
            assert after.status_code == 200
            assert after.json() == before
            assert before["occupied_ranges"] == [
                {"start_date": "2026-11-10", "end_date": "2026-11-12"}
            ]
    finally:
        recreated.state.engine.dispose()


def test_calendar_openapi_is_anonymous_and_has_only_allowed_fields(client: TestClient) -> None:
    schema = client.get("/api/openapi.json").json()
    operation = schema["paths"]["/api/public/equipment/{equipment_id}/calendar"]["get"]
    assert operation["security"] == []
    assert (
        set(schema["components"]["schemas"]["PublicCalendarRead"]["properties"]) == CALENDAR_FIELDS
    )
    assert "503" in operation["responses"]
