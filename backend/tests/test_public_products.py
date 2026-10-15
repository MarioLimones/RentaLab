"""Public models share stock while reservations keep independent physical units."""

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_public_calendar import CALENDAR_FIELDS, reserve
from test_public_catalogue import PUBLIC_FIELDS, create_equipment, get_availability, report_problem
from test_public_catalogue import visitor as visitor

DATES = {"start_date": "2026-11-15", "end_date": "2026-11-20"}
WINDOW = {"start_date": "2026-11-01", "end_date": "2026-12-01"}


@pytest.fixture
def twins(client: TestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    first = create_equipment(
        client,
        code="CAM-AURORA-01",
        name="Cámara Aurora S4",
        public_description="La ficha del modelo",
        technical_specs={"Resolución": "4K"},
    )
    second = create_equipment(
        client,
        code="CAM-AURORA-02",
        name="Cámara Aurora S4",
        public_description="Otra descripción de la unidad física",
    )
    return first, second


def calendar(browser: TestClient, equipment_id: int, **dates: str) -> dict[str, Any]:
    response = browser.get(f"/api/public/equipment/{equipment_id}/calendar", params=dates or WINDOW)
    assert response.status_code == 200, response.text
    assert set(response.json()) == CALENDAR_FIELDS
    return response.json()


def test_catalogue_publishes_one_model_without_stock_counts_and_keeps_aliases(
    client: TestClient, visitor: TestClient, twins: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    first, second = twins
    response = visitor.get("/api/public/equipment")
    assert response.status_code == 200
    assert len(response.json()) == 1
    product = response.json()[0]
    assert set(product) == PUBLIC_FIELDS
    assert product["id"] == first["id"]
    assert product["name"] == "Cámara Aurora S4"
    assert product["public_description"] == "La ficha del modelo"
    assert product["technical_specs"] == {"Resolución": "4K"}
    for unit in twins:
        detail = visitor.get(f"/api/public/equipment/{unit['id']}")
        assert detail.status_code == 200
        assert detail.json() == product
    inventory = client.get("/api/equipment").json()
    assert {item["id"] for item in inventory} == {first["id"], second["id"]}
    assert "CAM-AURORA-" not in response.text


def test_product_identity_normalizes_unicode_case_and_keeps_other_categories_separate(
    client: TestClient, visitor: TestClient
) -> None:
    first = create_equipment(client, code="UNICODE-01", name="Cámara Straße", category="Cámaras")
    alias = create_equipment(
        client, code="UNICODE-02", name="CA\u0301MARA STRASSE", category="CA\u0301MARAS"
    )
    other_category = create_equipment(
        client, code="UNICODE-03", name="Cámara Straße", category="Accesorios"
    )
    other_model = create_equipment(client, code="UNICODE-04", name="Cámara Strasse Plus")
    create_equipment(client, code="UNICODE-05", name="Cámara Straße", active=False)
    listing = visitor.get("/api/public/equipment").json()
    assert {item["id"] for item in listing} == {
        first["id"],
        other_category["id"],
        other_model["id"],
    }
    assert visitor.get(f"/api/public/equipment/{alias['id']}").json()["id"] == first["id"]


def test_active_representative_moves_to_remaining_unit_when_first_is_deactivated(
    client: TestClient, visitor: TestClient, twins: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    first, second = twins
    assert client.patch(f"/api/equipment/{first['id']}", json={"active": False}).status_code == 200
    listing = visitor.get("/api/public/equipment").json()
    assert [item["id"] for item in listing] == [second["id"]]
    assert visitor.get(f"/api/public/equipment/{first['id']}").status_code == 404
    assert visitor.get(f"/api/public/equipment/{second['id']}").json() == listing[0]


def test_public_availability_and_calendar_use_remaining_stock_and_refresh_after_cancellation(
    client: TestClient, visitor: TestClient, twins: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    first, second = twins
    reserve(client, first["id"], DATES["start_date"], DATES["end_date"])
    for unit in twins:
        assert get_availability(visitor, unit["id"], **DATES)["available"] is True
        assert calendar(visitor, unit["id"])["occupied_ranges"] == []
    assert (
        client.get(f"/api/equipment/{first['id']}/availability", params=DATES).json()["available"]
        is False
    )
    assert (
        client.get(f"/api/equipment/{second['id']}/availability", params=DATES).json()["available"]
        is True
    )

    last = reserve(client, second["id"], DATES["start_date"], DATES["end_date"])
    for unit in twins:
        assert get_availability(visitor, unit["id"], **DATES)["available"] is False
        result = calendar(visitor, unit["id"], **WINDOW, booking_start=DATES["start_date"])
        assert result["can_book"] is True
        assert result["occupied_ranges"] == [DATES]
        assert "2026-11-16" in result["unavailable_end_dates"]

    assert client.post(f"/api/reservations/{last['id']}/cancel").status_code == 200
    assert get_availability(visitor, first["id"], **DATES)["available"] is True
    refreshed = calendar(visitor, first["id"], **WINDOW, booking_start=DATES["start_date"])
    assert refreshed["occupied_ranges"] == []
    assert refreshed["unavailable_end_dates"] == []


@pytest.mark.parametrize(
    ("first_period", "second_period", "window", "booking_start", "last_valid_return"),
    [
        (
            ("2026-11-15", "2026-11-18"),
            ("2026-11-18", "2026-11-20"),
            WINDOW,
            "2026-11-15",
            "2026-11-18",
        ),
        (
            ("2026-10-29", "2026-11-02"),
            ("2026-11-02", "2026-11-05"),
            {"start_date": "2026-11-01", "end_date": "2026-11-08"},
            "2026-10-29",
            "2026-11-02",
        ),
        (
            ("2026-10-15", "2026-10-18"),
            ("2026-10-18", "2026-10-20"),
            WINDOW,
            "2026-10-15",
            "2026-10-18",
        ),
    ],
)
def test_free_days_do_not_offer_a_return_requiring_a_change_of_physical_unit(
    client: TestClient,
    visitor: TestClient,
    twins: tuple[dict[str, Any], dict[str, Any]],
    first_period: tuple[str, str],
    second_period: tuple[str, str],
    window: dict[str, str],
    booking_start: str,
    last_valid_return: str,
) -> None:
    first, second = twins
    reserve(client, first["id"], *first_period)
    reserve(client, second["id"], *second_period)
    result = calendar(visitor, first["id"], **window, booking_start=booking_start)
    assert result["occupied_ranges"] == []
    assert result["can_book"] is True
    expected = []
    day = date.fromisoformat(window["start_date"])
    while day < date.fromisoformat(window["end_date"]):
        if day.isoformat() > last_valid_return:
            expected.append(day.isoformat())
        day += timedelta(days=1)
    assert result["unavailable_end_dates"] == expected
    assert (
        get_availability(
            visitor, first["id"], start_date=booking_start, end_date=last_valid_return
        )["available"]
        is True
    )
    assert (
        get_availability(visitor, first["id"], start_date=booking_start, end_date=second_period[1])[
            "available"
        ]
        is False
    )


def test_calendar_intersects_occupancy_of_units_and_preserves_return_day_boundary(
    client: TestClient, visitor: TestClient, twins: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    first, second = twins
    reserve(client, first["id"], "2026-11-10", "2026-11-15")
    reserve(client, second["id"], "2026-11-12", "2026-11-18")
    result = calendar(visitor, first["id"], **WINDOW, booking_start="2026-11-09")
    assert result["occupied_ranges"] == [{"start_date": "2026-11-12", "end_date": "2026-11-15"}]
    assert "2026-11-12" not in result["unavailable_end_dates"]
    assert "2026-11-13" in result["unavailable_end_dates"]
    assert (
        get_availability(visitor, first["id"], start_date="2026-11-09", end_date="2026-11-12")[
            "available"
        ]
        is True
    )


@pytest.mark.parametrize("other_state", ["blocking_incident", "inactive"])
def test_blocked_or_inactive_units_do_not_supply_stock_or_calendar_availability(
    client: TestClient,
    visitor: TestClient,
    twins: tuple[dict[str, Any], dict[str, Any]],
    other_state: str,
) -> None:
    first, second = twins
    if other_state == "blocking_incident":
        report_problem(client, second["id"], blocking=True)
    else:
        assert (
            client.patch(f"/api/equipment/{second['id']}", json={"active": False}).status_code
            == 200
        )
    assert get_availability(visitor, first["id"], **DATES)["available"] is True
    reserve(client, first["id"], DATES["start_date"], DATES["end_date"])
    assert get_availability(visitor, first["id"], **DATES)["available"] is False
    assert calendar(visitor, first["id"])["occupied_ranges"] == [DATES]
    report_problem(client, first["id"], blocking=True)
    result = calendar(visitor, first["id"])
    assert result["can_book"] is False
    assert result["occupied_ranges"] == []


def test_blocked_representative_does_not_hide_free_unit_or_disclose_incident(
    client: TestClient, visitor: TestClient, twins: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    first, _second = twins
    report_problem(client, first["id"], blocking=True)
    assert get_availability(visitor, first["id"], **DATES)["available"] is True
    result = calendar(visitor, first["id"], **WINDOW, booking_start=DATES["start_date"])
    assert result["can_book"] is True
    assert result["occupied_ranges"] == result["unavailable_end_dates"] == []
    assert "PRIVATE-" not in str(result)
