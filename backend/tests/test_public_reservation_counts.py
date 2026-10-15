"""Catalogue counts describe confirmed ongoing/future rentals across model units."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from test_public_calendar import reserve
from test_public_catalogue import create_equipment, report_problem
from test_public_catalogue import visitor as visitor

from rentalab.clock import get_today_provider

TODAY = date(2030, 11, 15)


@pytest.fixture
def business_today(app: FastAPI) -> Iterator[None]:
    app.dependency_overrides[get_today_provider] = lambda: lambda: TODAY
    yield
    app.dependency_overrides.pop(get_today_provider, None)


@pytest.mark.usefixtures("business_today")
@pytest.mark.parametrize(
    ("start", "end", "cancelled", "expected"),
    [
        ("2030-11-01", "2030-11-05", False, 0),
        ("2030-11-13", "2030-11-15", False, 0),
        ("2030-11-14", "2030-11-16", False, 1),
        ("2030-11-15", "2030-11-17", False, 1),
        ("2030-11-18", "2030-11-20", False, 1),
        ("2030-11-14", "2030-11-16", True, 0),
        ("2030-11-18", "2030-11-20", True, 0),
    ],
)
def test_only_confirmed_rentals_with_days_remaining_are_counted(
    client: TestClient,
    visitor: TestClient,
    start: str,
    end: str,
    cancelled: bool,
    expected: int,
) -> None:
    equipment = create_equipment(client)
    booking = reserve(client, equipment["id"], start, end)
    if cancelled:
        assert client.post(f"/api/reservations/{booking['id']}/cancel").status_code == 200
    for browser in (visitor, client):
        listing = browser.get("/api/public/equipment")
        detail = browser.get(f"/api/public/equipment/{equipment['id']}")
        dates = browser.get(f"/api/public/equipment/{equipment['id']}/reservations")
        assert listing.status_code == detail.status_code == dates.status_code == 200
        assert listing.json()[0]["active_reservations_count"] == expected
        assert detail.json() == listing.json()[0]
        assert dates.json() == {
            "equipment_id": equipment["id"],
            "reservations": [{"start_date": start, "end_date": end}] if expected else [],
        }
        assert "PRIVATE-" not in listing.text + detail.text + dates.text
        assert "private-calendar@example.test" not in listing.text + detail.text + dates.text


@pytest.mark.usefixtures("business_today")
def test_counts_sum_reservations_across_normalized_active_model_units(
    client: TestClient, visitor: TestClient
) -> None:
    first = create_equipment(client, code="MODEL-01", name="Cámara Straße")
    alias = create_equipment(
        client, code="MODEL-02", name="CA\u0301MARA STRASSE", category="CA\u0301MARAS"
    )
    inactive = create_equipment(client, code="MODEL-03", name="Cámara Straße")
    other = create_equipment(client, code="MODEL-04", name="Cámara Straße", category="Accesorios")
    empty = create_equipment(client, code="MODEL-05", name="Modelo sin reservas")
    reserve(client, first["id"], "2030-11-14", "2030-11-17")
    reserve(client, first["id"], "2030-11-19", "2030-11-21")
    reserve(client, alias["id"], "2030-11-15", "2030-11-16")
    reserve(client, alias["id"], "2030-11-22", "2030-11-23")
    reserve(client, inactive["id"], "2030-11-15", "2030-11-16")
    reserve(client, other["id"], "2030-11-15", "2030-11-16")
    deactivated = client.patch(f"/api/equipment/{inactive['id']}", json={"active": False})
    assert deactivated.status_code == 200
    # Blocking availability does not cancel existing bookings or hide their count.
    report_problem(client, first["id"], blocking=True)

    response = visitor.get("/api/public/equipment")
    assert response.status_code == 200
    products = {item["id"]: item for item in response.json()}
    assert products[first["id"]]["active_reservations_count"] == 4
    assert products[other["id"]]["active_reservations_count"] == 1
    assert products[empty["id"]]["active_reservations_count"] == 0
    assert inactive["id"] not in products
    for unit in (first, alias):
        assert visitor.get(f"/api/public/equipment/{unit['id']}").json() == products[first["id"]]
        assert visitor.get(f"/api/public/equipment/{unit['id']}/reservations").json() == {
            "equipment_id": first["id"],
            "reservations": [
                {"start_date": "2030-11-14", "end_date": "2030-11-17"},
                {"start_date": "2030-11-15", "end_date": "2030-11-16"},
                {"start_date": "2030-11-19", "end_date": "2030-11-21"},
                {"start_date": "2030-11-22", "end_date": "2030-11-23"},
            ],
        }
    filtered = visitor.get("/api/public/equipment", params={"q": "STRASSE", "category": "Cámaras"})
    assert filtered.status_code == 200
    assert filtered.json() == [products[first["id"]]]


@pytest.mark.usefixtures("business_today")
def test_count_refreshes_after_booking_and_cancellation(
    client: TestClient, visitor: TestClient
) -> None:
    equipment = create_equipment(client)
    url = f"/api/public/equipment/{equipment['id']}"
    assert visitor.get(url).json()["active_reservations_count"] == 0
    assert visitor.get(f"{url}/reservations").json()["reservations"] == []
    booking = reserve(client, equipment["id"], "2030-11-18", "2030-11-20")
    assert visitor.get(url).json()["active_reservations_count"] == 1
    assert visitor.get(f"{url}/reservations").json()["reservations"] == [
        {"start_date": "2030-11-18", "end_date": "2030-11-20"}
    ]
    assert client.post(f"/api/reservations/{booking['id']}/cancel").status_code == 200
    assert visitor.get(url).json()["active_reservations_count"] == 0
    assert visitor.get("/api/public/equipment").json()[0]["active_reservations_count"] == 0
    assert visitor.get(f"{url}/reservations").json()["reservations"] == []


@pytest.mark.usefixtures("business_today")
def test_catalogue_aggregates_counts_in_one_query_without_reading_customer_records(
    app: FastAPI, client: TestClient, visitor: TestClient
) -> None:
    for index in range(6):
        equipment = create_equipment(client, code=f"MODEL-{index}", name=f"Modelo {index}")
        reserve(client, equipment["id"], "2030-11-18", "2030-11-20")
    queries: list[str] = []

    def record_query(_connection: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        if "reservations" in statement:
            queries.append(statement)

    event.listen(app.state.engine, "before_cursor_execute", record_query)
    try:
        response = visitor.get("/api/public/equipment")
    finally:
        event.remove(app.state.engine, "before_cursor_execute", record_query)
    assert response.status_code == 200
    assert [item["active_reservations_count"] for item in response.json()] == [1] * 6
    assert len(queries) == 1
    assert "count(" in queries[0].lower()
    assert "customer_name" not in queries[0]
    assert "customer_email" not in queries[0]
    assert "external_reference" not in queries[0]


def test_count_uses_madrid_date_across_utc_midnight(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, visitor: TestClient
) -> None:
    monkeypatch.setattr(
        "rentalab.clock.utc_now", lambda: datetime(2030, 11, 14, 23, 30, tzinfo=UTC)
    )
    equipment = create_equipment(client)
    reserve(client, equipment["id"], "2030-11-13", "2030-11-15")
    reserve(client, equipment["id"], "2030-11-15", "2030-11-17")
    listing = visitor.get("/api/public/equipment")
    detail = visitor.get(f"/api/public/equipment/{equipment['id']}")
    assert listing.status_code == detail.status_code == 200
    assert listing.json()[0]["active_reservations_count"] == 1
    assert detail.json() == listing.json()[0]
    assert visitor.get(f"/api/public/equipment/{equipment['id']}/reservations").json() == {
        "equipment_id": equipment["id"],
        "reservations": [{"start_date": "2030-11-15", "end_date": "2030-11-17"}],
    }
