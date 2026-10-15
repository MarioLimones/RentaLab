from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from test_me_reservations import TODAY, CustomerWorld, login_customer
from test_me_reservations import customer_world as customer_world

from rentalab.clock import get_today_provider
from rentalab.config import Settings
from rentalab.database import SQLITE_MAX_INTEGER
from rentalab.main import create_app
from rentalab.reservations.models import Reservation

BATCH_URL = "/api/me/reservations/batch"


@pytest.fixture
def products(customer_world: CustomerWorld, equipment_payload: dict) -> list[int]:
    ids = [customer_world.equipment_id]
    for number, name in [(2, "Trípode de prueba"), (3, "Micrófono de prueba")]:
        created = customer_world.admin.post(
            "/api/equipment", json={**equipment_payload, "code": f"PROD-{number}", "name": name}
        )
        assert created.status_code == 201, created.text
        ids.append(created.json()["id"])
    return ids


def batch_payload(products: list[int], **changes: object) -> dict:
    return {
        "equipment_ids": products,
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
        **changes,
    }


def test_batch_assigns_units_and_server_identity_with_one_write_transaction(
    app: FastAPI,
    customer_world: CustomerWorld,
    products: list[int],
    equipment_payload: dict,
) -> None:
    world = customer_world
    sibling = world.admin.post(
        "/api/equipment", json={**equipment_payload, "code": "CAM-002"}
    ).json()["id"]
    world.create(world.second)
    statements = []

    def observe(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.strip().upper())

    event.listen(app.state.engine, "before_cursor_execute", observe)
    try:
        response = world.first.post(BATCH_URL, json=batch_payload(products))
    finally:
        event.remove(app.state.engine, "before_cursor_execute", observe)
    assert response.status_code == 201, response.text
    actual = response.json()
    assert statements.count("BEGIN IMMEDIATE") == 1
    assert response.headers["location"] == "/api/me/reservations"
    assert response.headers["cache-control"] == "no-store"
    assert [row["equipment_id"] for row in actual] == [sibling, *products[1:]]
    for row in actual:
        assert row == {
            "id": row["id"],
            "equipment_id": row["equipment_id"],
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
            "status": "confirmed",
        }
    assert world.first.get("/api/me/reservations").json() == actual
    with app.state.session_factory() as session:
        rows = session.scalars(
            select(Reservation).where(Reservation.customer_user_id == world.first_id)
        ).all()
        assert len(rows) == 3
        assert all(row.origin == "portal" for row in rows)
        assert all(row.customer_name == "Alicia Prueba" for row in rows)
        assert all(row.customer_email == "alicia@example.test" for row in rows)
        assert all(row.external_reference is None for row in rows)


@pytest.mark.parametrize("unavailable", ["overlap", "blocking_incident", "inactive", "missing"])
def test_unavailable_middle_product_never_leaves_partial_reservations(
    app: FastAPI, customer_world: CustomerWorld, products: list[int], unavailable: str
) -> None:
    world = customer_world
    if unavailable == "overlap":
        world.create(world.second, equipment_id=products[1])
    elif unavailable == "blocking_incident":
        incident = world.admin.post(
            "/api/incidents",
            json={"equipment_id": products[1], "title": "PRIVATE-MAINTENANCE", "blocking": True},
        )
        assert incident.status_code == 201, incident.text
    elif unavailable == "inactive":
        assert (
            world.admin.patch(f"/api/equipment/{products[1]}", json={"active": False}).status_code
            == 200
        )
    else:
        products[1] = 999999
    before = world.admin.get("/api/reservations").json()
    response = world.first.post(BATCH_URL, json=batch_payload(products))
    assert response.status_code == (404 if unavailable == "missing" else 409), response.text
    assert "PRIVATE" not in response.text
    assert "blocking" not in response.text
    if unavailable != "missing":
        assert "no se ha creado ninguna reserva" in response.json()["detail"]
    assert world.first.get("/api/me/reservations").json() == []
    assert world.admin.get("/api/reservations").json() == before
    with app.state.session_factory() as session:
        assert len(session.scalars(select(Reservation)).all()) == len(before)


def test_product_aliases_are_rejected_before_writing(
    customer_world: CustomerWorld, equipment_payload: dict
) -> None:
    world = customer_world
    alias = world.admin.post(
        "/api/equipment",
        json={
            **equipment_payload,
            "code": "CAM-ALIAS",
            "name": "  CÁMARA DE PRUEBA  ",
            "category": "  CÁMARAS  ",
        },
    ).json()["id"]
    response = world.first.post(BATCH_URL, json=batch_payload([world.equipment_id, alias]))
    assert response.status_code == 409, response.text
    assert "una sola vez" in response.json()["detail"]
    assert world.admin.get("/api/reservations").json() == []


@pytest.mark.parametrize(
    "invalid_ids",
    [
        [],
        [0],
        [-1],
        [True],
        [1.0],
        ["1"],
        [None],
        [SQLITE_MAX_INTEGER + 1],
        [1, 1],
        list(range(1, 52)),
    ],
)
def test_batch_requires_one_to_fifty_distinct_strict_positive_ids(
    customer_world: CustomerWorld, invalid_ids: list
) -> None:
    world = customer_world
    response = world.first.post(BATCH_URL, json=batch_payload(invalid_ids))
    assert response.status_code == 422, response.text
    assert world.admin.get("/api/reservations").json() == []


@pytest.mark.parametrize(
    "extra",
    [
        {"customer_user_id": 2},
        {"customer_name": "Falsa identidad"},
        {"customer_email": "bruno@example.test"},
        {"status": "cancelled"},
        {"origin": "csv"},
        {"external_reference": "PRIVATE-REFERENCE"},
        {"equipment_id": 1},
    ],
)
def test_batch_rejects_identity_and_administrative_fields(
    customer_world: CustomerWorld, products: list[int], extra: dict
) -> None:
    world = customer_world
    response = world.first.post(BATCH_URL, json=batch_payload(products, **extra))
    assert response.status_code == 422, response.text
    assert world.admin.get("/api/reservations").json() == []


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"start_date": "2026-10-14", "end_date": "2026-10-16"}, 409),
        ({"end_date": "2026-11-10"}, 422),
        ({"start_date": "2026-11-10T00:00:00"}, 422),
        ({"start_date": 0}, 422),
        ({"end_date": "2026-02-30"}, 422),
    ],
)
def test_batch_rejects_past_or_invalid_shared_dates(
    customer_world: CustomerWorld, products: list[int], changes: dict, expected: int
) -> None:
    response = customer_world.first.post(BATCH_URL, json=batch_payload(products, **changes))
    assert response.status_code == expected, response.text
    assert customer_world.admin.get("/api/reservations").json() == []


def test_batch_allows_today_and_adjacent_reservations(
    customer_world: CustomerWorld, products: list[int]
) -> None:
    world = customer_world
    first = world.first.post(
        BATCH_URL, json=batch_payload(products, start_date=TODAY.isoformat(), end_date="2026-11-10")
    )
    assert first.status_code == 201, first.text
    adjacent = world.second.post(BATCH_URL, json=batch_payload(products))
    assert adjacent.status_code == 201, adjacent.text


def test_batch_requires_customer_session_and_csrf(
    app: FastAPI, customer_world: CustomerWorld, products: list[int]
) -> None:
    world = customer_world
    with TestClient(app) as visitor:
        assert visitor.post(BATCH_URL, json=batch_payload(products)).status_code == 401
    assert world.admin.post(BATCH_URL, json=batch_payload(products)).status_code == 403
    original = world.first.headers.pop("X-CSRF-Token")
    try:
        assert world.first.post(BATCH_URL, json=batch_payload(products)).status_code == 403
        world.first.headers["X-CSRF-Token"] = "wrong-csrf"
        assert world.first.post(BATCH_URL, json=batch_payload(products)).status_code == 403
    finally:
        world.first.headers["X-CSRF-Token"] = original
    assert world.admin.get("/api/reservations").json() == []


@pytest.mark.parametrize("competitor", ["customer", "admin"])
@pytest.mark.parametrize("batch_first", [False, True])
def test_batch_and_single_admin_or_customer_requests_serialize_without_partial_writes(
    app: FastAPI,
    settings: Settings,
    customer_world: CustomerWorld,
    products: list[int],
    competitor: str,
    batch_first: bool,
) -> None:
    world = customer_world
    second_app = create_app(settings)
    second_app.dependency_overrides[get_today_provider] = lambda: lambda: TODAY
    first_has_lock, second_attempted_write = Event(), Event()

    def hold_first_write(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            first_has_lock.set()
            assert second_attempted_write.wait(timeout=5), "Competing write did not attempt SQL"

    def observe_second_write(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            second_attempted_write.set()

    single_url = "/api/me/reservations" if competitor == "customer" else "/api/reservations"
    single_data = world.payload(equipment_id=products[1])
    if competitor == "admin":
        single_data.update(
            customer_name="Cliente administrativo", customer_email="booking@example.test"
        )
    first_browser = world.first if batch_first or competitor == "customer" else world.admin
    try:
        with TestClient(second_app) as second_browser:
            login_customer(
                second_browser,
                "admin-phase-c@example.test"
                if batch_first and competitor == "admin"
                else "bruno@example.test",
            )
            event.listen(app.state.engine, "after_cursor_execute", hold_first_write)
            event.listen(second_app.state.engine, "before_cursor_execute", observe_second_write)
            try:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    first = executor.submit(
                        first_browser.post,
                        BATCH_URL if batch_first else single_url,
                        json=batch_payload(products) if batch_first else single_data,
                    )
                    assert first_has_lock.wait(timeout=5), "First request did not acquire lock"
                    second = executor.submit(
                        second_browser.post,
                        single_url if batch_first else BATCH_URL,
                        json=single_data if batch_first else batch_payload(products),
                    )
                    responses = [first.result(timeout=10), second.result(timeout=10)]
            finally:
                event.remove(app.state.engine, "after_cursor_execute", hold_first_write)
                event.remove(second_app.state.engine, "before_cursor_execute", observe_second_write)
        assert [response.status_code for response in responses] == [201, 409]
        with app.state.session_factory() as session:
            rows = session.scalars(select(Reservation)).all()
            assert len(rows) == (3 if batch_first else 1)
            assert {row.equipment_id for row in rows} == (
                set(products) if batch_first else {products[1]}
            )
            assert all(row.status == "confirmed" for row in rows)
    finally:
        second_app.state.engine.dispose()


def test_batch_reads_business_day_after_acquiring_lock(
    app: FastAPI, settings: Settings, customer_world: CustomerWorld, products: list[int]
) -> None:
    second_app = create_app(settings)
    day = [date(2026, 11, 9)]
    requested_days: list[date] = []
    attempted_write = Event()

    def business_day() -> date:
        requested_days.append(day[0])
        return day[0]

    def observe_write(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            attempted_write.set()

    second_app.dependency_overrides[get_today_provider] = lambda: business_day
    try:
        with TestClient(second_app) as browser:
            login_customer(browser, "alicia@example.test")
            with app.state.engine.connect() as lock_owner:
                lock_owner.exec_driver_sql("BEGIN IMMEDIATE")
                event.listen(second_app.state.engine, "before_cursor_execute", observe_write)
                try:
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        pending = executor.submit(
                            browser.post, BATCH_URL, json=batch_payload(products)
                        )
                        assert attempted_write.wait(timeout=5), "Batch did not attempt SQL"
                        assert requested_days == []
                        day[0] = date(2026, 11, 11)
                        lock_owner.rollback()
                        response = pending.result(timeout=10)
                finally:
                    event.remove(second_app.state.engine, "before_cursor_execute", observe_write)
        assert response.status_code == 409, response.text
        assert requested_days == [date(2026, 11, 11)]
        assert customer_world.admin.get("/api/reservations").json() == []
    finally:
        second_app.state.engine.dispose()
