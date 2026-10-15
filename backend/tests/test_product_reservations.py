from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from test_imports import import_csv, make_csv, order_row
from test_me_reservations import TODAY, CustomerWorld, login_customer
from test_me_reservations import customer_world as customer_world

from rentalab.clock import get_today_provider
from rentalab.config import Settings
from rentalab.main import create_app
from rentalab.reservations.models import Reservation
from rentalab.reservations.repository import ReservationRepository
from rentalab.reservations.schemas import ReservationCreate
from rentalab.reservations.service import ReservationConflict, ReservationService


@pytest.fixture
def second_unit(customer_world: CustomerWorld, equipment_payload: dict) -> int:
    response = customer_world.admin.post(
        "/api/equipment", json={**equipment_payload, "code": "CAM-002"}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def admin_reserve(world: CustomerWorld, **changes: object) -> dict:
    response = world.admin.post(
        "/api/reservations",
        json={
            **world.payload(**changes),
            "customer_name": "Cliente administrativo",
            "customer_email": "admin-booking@example.test",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_product_books_two_units_independently_and_cancellation_restores_capacity(
    app: FastAPI, customer_world: CustomerWorld, second_unit: int
) -> None:
    world = customer_world
    first = world.create()
    second = world.create(world.second)
    assert [first["equipment_id"], second["equipment_id"]] == [world.equipment_id, second_unit]
    exhausted = world.first.post("/api/me/reservations", json=world.payload())
    assert exhausted.status_code == 409
    assert world.first.get("/api/me/reservations").json() == [first]
    assert world.second.get("/api/me/reservations").json() == [second]
    assert world.first.post(f"/api/me/reservations/{second['id']}/cancel").status_code == 404
    assert world.first.post(f"/api/me/reservations/{first['id']}/cancel").status_code == 200
    replacement = world.create()
    assert replacement["equipment_id"] == world.equipment_id
    with app.state.session_factory() as session:
        reservations = session.scalars(select(Reservation).order_by(Reservation.id)).all()
        assert len(reservations) == 3
        assert [row.status for row in reservations] == ["cancelled", "confirmed", "confirmed"]
        assert [row.customer_user_id for row in reservations] == [
            world.first_id,
            world.second_id,
            world.first_id,
        ]
        assert all(row.origin == "portal" for row in reservations)


@pytest.mark.parametrize("unavailable", ["inactive", "blocking_incident"])
def test_unavailable_units_do_not_add_capacity_and_recover_when_reenabled(
    customer_world: CustomerWorld, second_unit: int, unavailable: str
) -> None:
    world = customer_world
    world.create()
    incident_id = None
    if unavailable == "inactive":
        assert (
            world.admin.patch(f"/api/equipment/{second_unit}", json={"active": False}).status_code
            == 200
        )
    else:
        incident = world.admin.post(
            "/api/incidents",
            json={"equipment_id": second_unit, "title": "PRIVATE-MAINTENANCE", "blocking": True},
        )
        assert incident.status_code == 201, incident.text
        incident_id = incident.json()["id"]
    unavailable_response = world.second.post("/api/me/reservations", json=world.payload())
    assert unavailable_response.status_code == 409
    assert "PRIVATE" not in unavailable_response.text
    assert "blocking" not in unavailable_response.text
    if unavailable == "inactive":
        assert (
            world.admin.patch(f"/api/equipment/{second_unit}", json={"active": True}).status_code
            == 200
        )
    else:
        assert (
            world.admin.patch(f"/api/incidents/{incident_id}", json={"blocking": False}).status_code
            == 200
        )
    assert world.create(world.second)["equipment_id"] == second_unit


def test_blocked_representative_can_allocate_healthy_sibling(
    customer_world: CustomerWorld, second_unit: int
) -> None:
    world = customer_world
    blocked = world.admin.post(
        "/api/incidents",
        json={"equipment_id": world.equipment_id, "title": "En reparación", "blocking": True},
    )
    assert blocked.status_code == 201, blocked.text
    assert world.create()["equipment_id"] == second_unit
    assert world.second.post("/api/me/reservations", json=world.payload()).status_code == 409


def test_inactive_requested_unit_does_not_allow_a_hidden_product_link(
    customer_world: CustomerWorld, second_unit: int
) -> None:
    world = customer_world
    assert (
        world.admin.patch(
            f"/api/equipment/{world.equipment_id}", json={"active": False}
        ).status_code
        == 200
    )
    assert world.first.post("/api/me/reservations", json=world.payload()).status_code == 409
    assert world.create(equipment_id=second_unit)["equipment_id"] == second_unit


def test_fragmented_capacity_cannot_change_units_halfway_through_a_booking(
    customer_world: CustomerWorld, second_unit: int
) -> None:
    world = customer_world
    admin_reserve(world, end_date="2026-11-11")
    admin_reserve(world, equipment_id=second_unit, start_date="2026-11-11")
    response = world.first.post("/api/me/reservations", json=world.payload())
    assert response.status_code == 409
    assert world.first.get("/api/me/reservations").json() == []
    assert len(world.admin.get("/api/reservations").json()) == 2
    # The end day remains exclusive for each physical unit.
    first = world.create(start_date="2026-11-11")
    second = world.create(world.second, end_date="2026-11-11")
    assert [first["equipment_id"], second["equipment_id"]] == [world.equipment_id, second_unit]


@pytest.mark.parametrize(
    "changes",
    [{"name": "Otro modelo"}, {"category": "Ópticas"}],
)
def test_allocation_does_not_borrow_a_different_product_or_category(
    customer_world: CustomerWorld, equipment_payload: dict, changes: dict
) -> None:
    world = customer_world
    other = world.admin.post(
        "/api/equipment", json={**equipment_payload, "code": "CAM-OTHER", **changes}
    )
    assert other.status_code == 201, other.text
    world.create()
    assert world.second.post("/api/me/reservations", json=world.payload()).status_code == 409
    assert (
        world.create(world.second, equipment_id=other.json()["id"])["equipment_id"]
        == (other.json()["id"])
    )


def test_normalized_product_name_and_category_share_capacity(
    customer_world: CustomerWorld, second_unit: int
) -> None:
    world = customer_world
    updated = world.admin.patch(
        f"/api/equipment/{second_unit}",
        json={"name": "  CÁMARA DE PRUEBA  ", "category": "  CÁMARAS  "},
    )
    assert updated.status_code == 200, updated.text
    world.create()
    assert world.create(world.second)["equipment_id"] == second_unit


def test_admin_csv_and_explicit_demo_calls_keep_the_requested_physical_unit(
    app: FastAPI, customer_world: CustomerWorld, second_unit: int
) -> None:
    world = customer_world
    world.create()
    admin = world.admin.post(
        "/api/reservations",
        json={
            **world.payload(),
            "customer_name": "Cliente administrativo",
            "customer_email": "admin-booking@example.test",
        },
    )
    assert admin.status_code == 409
    report = import_csv(world.admin, make_csv([order_row("EXACT-UNIT-CSV")]))
    assert report["totals"]["rejected"] == 1
    with app.state.session_factory() as session:
        service = ReservationService(ReservationRepository(session))
        with pytest.raises(ReservationConflict):
            service.create_for_customer(
                ReservationCreate(
                    **world.payload(),
                    customer_name="Alicia Prueba",
                    customer_email="alicia@example.test",
                ),
                customer_user_id=world.first_id,
                today=lambda: TODAY,
            )
    assert world.create(world.second)["equipment_id"] == second_unit


def test_parallel_bookings_never_overbook_two_units(
    app: FastAPI, settings: Settings, customer_world: CustomerWorld, second_unit: int
) -> None:
    world = customer_world
    other_apps = [create_app(settings), create_app(settings)]
    for other_app in other_apps:
        other_app.dependency_overrides[get_today_provider] = lambda: lambda: TODAY
    first_has_lock = Event()
    waiting_writers = [Event(), Event()]

    def hold_first_write(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            first_has_lock.set()
            for waiting_writer in waiting_writers:
                assert waiting_writer.wait(timeout=5), "Competing request did not attempt its write"

    def observe_write(waiting_writer: Event):
        def observe(_connection, _cursor, statement, _parameters, _context, _executemany):
            if statement.strip().upper() == "BEGIN IMMEDIATE":
                waiting_writer.set()

        return observe

    observers = [observe_write(writer) for writer in waiting_writers]
    try:
        with ExitStack() as stack:
            browsers = [stack.enter_context(TestClient(other_app)) for other_app in other_apps]
            login_customer(browsers[0], "bruno@example.test")
            login_customer(browsers[1], "alicia@example.test")
            event.listen(app.state.engine, "after_cursor_execute", hold_first_write)
            for other_app, observer in zip(other_apps, observers, strict=True):
                event.listen(other_app.state.engine, "before_cursor_execute", observer)
            try:
                with ThreadPoolExecutor(max_workers=3) as executor:
                    first = executor.submit(
                        world.first.post, "/api/me/reservations", json=world.payload()
                    )
                    assert first_has_lock.wait(timeout=5), "First request did not acquire its lock"
                    others = [
                        executor.submit(browser.post, "/api/me/reservations", json=world.payload())
                        for browser in browsers
                    ]
                    responses = [first.result(timeout=10)] + [
                        future.result(timeout=10) for future in others
                    ]
            finally:
                event.remove(app.state.engine, "after_cursor_execute", hold_first_write)
                for other_app, observer in zip(other_apps, observers, strict=True):
                    event.remove(other_app.state.engine, "before_cursor_execute", observer)
        assert sorted(response.status_code for response in responses) == [201, 201, 409]
        confirmed = [response.json() for response in responses if response.status_code == 201]
        assert {reservation["equipment_id"] for reservation in confirmed} == {
            world.equipment_id,
            second_unit,
        }
        with app.state.session_factory() as session:
            reservations = session.scalars(select(Reservation)).all()
            assert len(reservations) == 2
            assert {reservation.equipment_id for reservation in reservations} == {
                world.equipment_id,
                second_unit,
            }
            assert all(reservation.status == "confirmed" for reservation in reservations)
    finally:
        for other_app in other_apps:
            other_app.state.engine.dispose()
