from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

PUBLIC_FIELDS = {
    "id",
    "name",
    "category",
    "public_description",
    "technical_specs",
    "image_url",
    "image_fallback_url",
    "active_reservations_count",
}
AVAILABILITY_FIELDS = {"equipment_id", "start_date", "end_date", "available", "status"}
DATES = {"start_date": "2026-11-10", "end_date": "2026-11-12"}


@pytest.fixture
def visitor(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as browser:
        yield browser


def create_equipment(admin: TestClient, **changes: object) -> dict[str, Any]:
    response = admin.post(
        "/api/equipment",
        json={
            "code": "PRIVATE-CODE-001",
            "name": "Cámara de prueba",
            "category": "Cámaras",
            "description": "PRIVATE-INTERNAL-NOTE",
            **changes,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def book_equipment(admin: TestClient, equipment_id: object) -> dict[str, Any]:
    response = admin.post(
        "/api/reservations",
        json={
            "equipment_id": equipment_id,
            "customer_name": "PRIVATE-CUSTOMER-NAME",
            "customer_email": "private-customer@example.test",
            "external_reference": "PRIVATE-BOOKING-REFERENCE",
            **DATES,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def report_problem(admin: TestClient, equipment_id: object, blocking: bool) -> dict[str, Any]:
    response = admin.post(
        "/api/incidents",
        json={
            "equipment_id": equipment_id,
            "title": "PRIVATE-FAULT-TITLE",
            "description": "PRIVATE-FAULT-DESCRIPTION",
            "priority": "high",
            "blocking": blocking,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def get_availability(visitor: TestClient, equipment_id: object, **dates: str) -> dict[str, Any]:
    response = visitor.get(
        f"/api/public/equipment/{equipment_id}/availability", params=dates or DATES
    )
    assert response.status_code == 200, response.text
    assert set(response.json()) == AVAILABILITY_FIELDS
    return response.json()


def test_empty_catalogue_is_public(visitor: TestClient) -> None:
    response = visitor.get("/api/public/equipment")
    assert response.status_code == 200
    assert response.json() == []


def test_catalogue_projects_only_public_fields_and_local_image_fallback(
    client: TestClient, visitor: TestClient
) -> None:
    equipment = create_equipment(
        client,
        public_description="Cámara ficticia compacta para entrevistas y eventos.",
        technical_specs={"Resolución": "4K UHD", "Conexiones": "HDMI, USB-C"},
    )
    expected = {
        "id": equipment["id"],
        "name": "Cámara de prueba",
        "category": "Cámaras",
        "public_description": "Cámara ficticia compacta para entrevistas y eventos.",
        "technical_specs": {"Resolución": "4K UHD", "Conexiones": "HDMI, USB-C"},
        "image_url": None,
        "image_fallback_url": "/api/public/images/equipment-placeholder.svg",
        "active_reservations_count": 0,
    }
    for browser in (visitor, client):
        listing = browser.get("/api/public/equipment")
        detail = browser.get(f"/api/public/equipment/{equipment['id']}")
        assert listing.status_code == detail.status_code == 200
        assert listing.json() == [expected]
        assert detail.json() == expected
        assert set(detail.json()) == PUBLIC_FIELDS
        assert "PRIVATE-" not in listing.text + detail.text
    image = visitor.get(expected["image_fallback_url"])
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in image.text
    assert "http://" not in image.text.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in image.text


def test_catalogue_excludes_inactive_groups_models_and_orders_by_name_then_id(
    client: TestClient, visitor: TestClient
) -> None:
    last = create_equipment(client, code="EQUIP-01", name="Zeta")
    first = create_equipment(client, code="EQUIP-02", name="Alfa")
    create_equipment(client, code="EQUIP-03", name="Alfa")
    create_equipment(client, code="EQUIP-04", name="A oculto", active=False)
    response = visitor.get("/api/public/equipment")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [first["id"], last["id"]]


@pytest.mark.parametrize("query", ["CÁMARA", "cámara", "  CÁMARA  ", "mara de pru"])
def test_search_matches_name_substrings_with_unicode_casefold(
    client: TestClient, visitor: TestClient, query: str
) -> None:
    match = create_equipment(client)
    create_equipment(client, code="LIGHT-02", name="Foco LED", description="Cámara interna")
    response = visitor.get("/api/public/equipment", params={"q": query})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [match["id"]]


@pytest.mark.parametrize("query", ["%", "_", "' OR 1=1 --"])
def test_search_treats_sql_wildcards_and_syntax_as_literal_text(
    client: TestClient, visitor: TestClient, query: str
) -> None:
    match = create_equipment(client, name=f"Equipo {query}")
    create_equipment(client, code="OTHER-02", name="Equipo diferente")
    response = visitor.get("/api/public/equipment", params={"q": query})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [match["id"]]


@pytest.mark.parametrize("category", ["CÁMARAS", "cámaras", "  CáMaRaS  "])
def test_category_filter_is_exact_and_case_insensitive(
    client: TestClient, visitor: TestClient, category: str
) -> None:
    match = create_equipment(client)
    create_equipment(client, code="OTHER-02", category="Cámaras de acción")
    response = visitor.get("/api/public/equipment", params={"category": category})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [match["id"]]


def test_search_and_category_combine_and_unknown_values_return_empty_list(
    client: TestClient, visitor: TestClient
) -> None:
    match = create_equipment(client, name="Compacta 4K")
    create_equipment(client, code="OTHER-02", name="Compacta LED", category="Iluminación")
    create_equipment(client, code="OTHER-03", name="Profesional", category="Cámaras")
    response = visitor.get("/api/public/equipment", params={"q": "compacta", "category": "cámaras"})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [match["id"]]
    assert visitor.get("/api/public/equipment", params={"q": "ausente"}).json() == []
    assert visitor.get("/api/public/equipment", params={"category": "ausente"}).json() == []


def test_filters_use_full_unicode_casefold_and_ignore_blank_values(
    client: TestClient, visitor: TestClient
) -> None:
    equipment = create_equipment(client, name="Straße cámara", category="Maße")
    response = visitor.get("/api/public/equipment", params={"q": "STRASSE", "category": "MASSE"})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [equipment["id"]]
    unfiltered = visitor.get("/api/public/equipment", params={"q": "  ", "category": ""})
    assert unfiltered.status_code == 200
    assert [item["id"] for item in unfiltered.json()] == [equipment["id"]]


@pytest.mark.parametrize(
    "filters",
    [{"q": "x" * 121}, {"category": "x" * 81}, {"q": "bad\x00text"}, {"active": "false"}],
)
def test_catalogue_rejects_invalid_or_administrative_filters(
    visitor: TestClient, filters: dict[str, str]
) -> None:
    assert visitor.get("/api/public/equipment", params=filters).status_code == 422


@pytest.mark.parametrize("suffix", ["", "/availability"])
def test_inactive_and_missing_equipment_have_identical_public_404(
    client: TestClient, visitor: TestClient, suffix: str
) -> None:
    equipment = create_equipment(client, active=False)
    inactive = visitor.get(f"/api/public/equipment/{equipment['id']}{suffix}")
    missing = visitor.get(f"/api/public/equipment/999999{suffix}")
    assert inactive.status_code == missing.status_code == 404
    assert inactive.json() == missing.json() == {"detail": "El equipo no existe"}


def test_without_dates_requires_selection_and_does_not_query_private_history(
    app: FastAPI, client: TestClient, visitor: TestClient
) -> None:
    equipment = create_equipment(client)
    book_equipment(client, equipment["id"])
    report_problem(client, equipment["id"], blocking=True)
    queries: list[str] = []

    def record_query(_connection: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        queries.append(statement)

    event.listen(app.state.engine, "before_cursor_execute", record_query)
    try:
        response = visitor.get(f"/api/public/equipment/{equipment['id']}/availability")
    finally:
        event.remove(app.state.engine, "before_cursor_execute", record_query)
    assert response.status_code == 200
    assert response.json() == {
        "equipment_id": equipment["id"],
        "start_date": None,
        "end_date": None,
        "available": None,
        "status": "select_dates",
    }
    assert not any("reservations" in query or "incidents" in query for query in queries)


@pytest.mark.parametrize(
    "dates",
    [
        {"start_date": "2026-11-10"},
        {"end_date": "2026-11-12"},
        {"start_date": "2026-11-10", "end_date": "2026-11-10"},
        {"start_date": "2026-11-12", "end_date": "2026-11-10"},
        {"start_date": "2026-02-30", "end_date": "2026-11-12"},
        {"start_date": "2026-11-10T00:00:00", "end_date": "2026-11-12"},
        {"start_date": "2026-1-01", "end_date": "2026-11-12"},
        {"start_date": "1794268800", "end_date": "2026-11-12"},
        {"start_date": "", "end_date": "2026-11-12"},
    ],
)
def test_invalid_and_partial_date_ranges_are_422(
    client: TestClient, visitor: TestClient, dates: dict[str, str]
) -> None:
    equipment = create_equipment(client)
    response = visitor.get(f"/api/public/equipment/{equipment['id']}/availability", params=dates)
    assert response.status_code == 422


def test_free_equipment_returns_dates_and_available_status(
    client: TestClient, visitor: TestClient
) -> None:
    equipment = create_equipment(client)
    assert get_availability(visitor, equipment["id"]) == {
        "equipment_id": equipment["id"],
        **DATES,
        "available": True,
        "status": "available",
    }


@pytest.mark.parametrize(
    ("start_date", "end_date", "expected"),
    [
        ("2026-11-09", "2026-11-10", True),
        ("2026-11-12", "2026-11-13", True),
        ("2026-11-09", "2026-11-11", False),
        ("2026-11-11", "2026-11-13", False),
        ("2026-11-10", "2026-11-12", False),
        ("2026-11-09", "2026-11-13", False),
        ("2026-11-10", "2026-11-11", False),
    ],
)
def test_public_and_administrative_availability_share_day_overlap_rules(
    client: TestClient,
    visitor: TestClient,
    start_date: str,
    end_date: str,
    expected: bool,
) -> None:
    equipment = create_equipment(client)
    book_equipment(client, equipment["id"])
    dates = {"start_date": start_date, "end_date": end_date}
    public = get_availability(visitor, equipment["id"], **dates)
    administrative = client.get(f"/api/equipment/{equipment['id']}/availability", params=dates)
    assert administrative.status_code == 200
    assert public["available"] is administrative.json()["available"] is expected
    assert public["status"] == ("available" if expected else "unavailable")


def test_cancelled_booking_frees_its_days_and_another_product_is_unaffected(
    client: TestClient, visitor: TestClient
) -> None:
    equipment = create_equipment(client)
    other = create_equipment(client, code="OTHER-02", name="Otro modelo")
    booking = book_equipment(client, equipment["id"])
    assert get_availability(visitor, equipment["id"])["available"] is False
    assert get_availability(visitor, other["id"])["available"] is True
    assert client.post(f"/api/reservations/{booking['id']}/cancel").status_code == 200
    assert get_availability(visitor, equipment["id"])["available"] is True


@pytest.mark.parametrize("blocking", [False, True])
@pytest.mark.parametrize("status", ["open", "in_progress", "resolved"])
def test_incident_rules_are_shared_without_revealing_faults(
    client: TestClient, visitor: TestClient, blocking: bool, status: str
) -> None:
    equipment = create_equipment(client)
    incident = report_problem(client, equipment["id"], blocking)
    if status != "open":
        change: dict[str, object] = {"status": status}
        if status == "resolved":
            change["resolution"] = "PRIVATE-FAULT-RESOLUTION"
        assert (
            client.patch(f"/api/incidents/{incident['id']}/status", json=change).status_code == 200
        )
    expected = not (blocking and status != "resolved")
    for browser in (visitor, client):
        public = get_availability(browser, equipment["id"])
        assert public["available"] is expected
        assert public["status"] == ("available" if expected else "unavailable")
        assert "PRIVATE-" not in str(public)
    administrative = client.get(f"/api/equipment/{equipment['id']}/availability", params=DATES)
    assert administrative.status_code == 200
    assert administrative.json()["available"] is expected


def test_private_customer_and_booking_data_do_not_appear_in_any_public_response(
    client: TestClient, visitor: TestClient
) -> None:
    equipment = create_equipment(client)
    book_equipment(client, equipment["id"])
    report_problem(client, equipment["id"], blocking=True)
    paths = [
        "/api/public/equipment",
        f"/api/public/equipment/{equipment['id']}",
        f"/api/public/equipment/{equipment['id']}/availability",
    ]
    for browser in (visitor, client):
        for path in paths:
            response = browser.get(path, params=DATES if path.endswith("availability") else None)
            assert response.status_code == 200
            assert "PRIVATE-" not in response.text
            assert "private-customer@example.test" not in response.text
            rows = response.json() if isinstance(response.json(), list) else [response.json()]
            for row in rows:
                expected_keys = (
                    AVAILABILITY_FIELDS if path.endswith("availability") else PUBLIC_FIELDS
                )
                assert set(row) == expected_keys
