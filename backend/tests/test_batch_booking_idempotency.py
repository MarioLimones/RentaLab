"""The same durable intent protects saved-list batches, including one-product batches."""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_booking_idempotency import intent
from test_me_reservations import CustomerWorld, login_customer
from test_me_reservations import customer_world as customer_world
from test_product_reservations import second_unit as second_unit

from rentalab.clock import get_today_provider
from rentalab.config import Settings
from rentalab.main import create_app
from rentalab.reservations.models import (
    BookingRequestReservation,
    CustomerBookingRequest,
    Reservation,
)

SINGLE_URL = "/api/me/reservations"
URL = f"{SINGLE_URL}/batch"


def payload(world: CustomerWorld, ids: list[int], **changes: object) -> dict:
    return {
        "equipment_ids": ids,
        "start_date": world.payload()["start_date"],
        "end_date": world.payload()["end_date"],
        **changes,
    }


def other_model(world: CustomerWorld, index: int = 0) -> int:
    response = world.admin.post(
        "/api/equipment",
        json={"code": f"OTHER-{index}", "name": "Otro modelo", "category": "Audio"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_one_product_batch_lost_response_retry_does_not_consume_second_unit(
    app: FastAPI, customer_world: CustomerWorld, second_unit: int
) -> None:
    world = customer_world
    headers = intent()
    body = payload(world, [world.equipment_id])
    original = world.first.post(URL, json=body, headers=headers)
    assert original.status_code == 201
    replay = world.first.post(URL, json=body, headers=headers)
    assert replay.status_code == 201
    assert replay.json() == original.json()
    assert original.json()[0]["equipment_id"] != second_unit
    with app.state.session_factory() as session:
        assert len(session.scalars(select(Reservation)).all()) == 1
        assert len(session.scalars(select(CustomerBookingRequest)).all()) == 1
        assert len(session.scalars(select(BookingRequestReservation)).all()) == 1


def test_batch_replay_after_restart_preserves_order_and_current_status_despite_past_or_inactive(
    app: FastAPI, settings: Settings, customer_world: CustomerWorld, second_unit: int
) -> None:
    world = customer_world
    other = other_model(world)
    other_model(world, 1)
    body = payload(world, [other, world.equipment_id])
    headers = intent()
    original = world.first.post(URL, json=body, headers=headers)
    assert original.status_code == 201
    rows = original.json()
    assert [row["equipment_id"] for row in rows] == [other, world.equipment_id]
    cancelled = world.first.post(f"{SINGLE_URL}/{rows[0]['id']}/cancel")
    assert cancelled.status_code == 200
    assert world.admin.patch(f"/api/equipment/{other}", json={"active": False}).status_code == 200
    expected = [cancelled.json(), rows[1]]
    recreated = create_app(settings)
    recreated.dependency_overrides[get_today_provider] = lambda: lambda: date(2026, 12, 1)
    try:
        with TestClient(recreated) as browser:
            login_customer(browser, "alicia@example.test")
            replay = browser.post(URL, json=body, headers=headers)
            assert replay.status_code == 201, replay.text
            assert replay.json() == expected
            assert replay.headers["location"] == SINGLE_URL
        with app.state.session_factory() as session:
            assert len(session.scalars(select(Reservation)).all()) == 2
            request = session.scalars(select(CustomerBookingRequest)).one()
            assert request.operation == "batch"
            assert [item.requested_equipment_id for item in request.items] == body["equipment_ids"]
            assert [item.position for item in request.items] == [0, 1]
    finally:
        recreated.state.engine.dispose()
    assert second_unit != rows[1]["equipment_id"]


@pytest.mark.parametrize("change", ["order", "products", "start", "end"])
def test_batch_key_reuse_with_different_original_payload_is_a_conflict(
    app: FastAPI, customer_world: CustomerWorld, change: str
) -> None:
    world = customer_world
    other = other_model(world)
    body = payload(world, [other, world.equipment_id])
    headers = intent()
    original = world.first.post(URL, json=body, headers=headers)
    assert original.status_code == 201
    changed = {
        "order": payload(world, [world.equipment_id, other]),
        "products": payload(world, [world.equipment_id]),
        "start": payload(world, [other, world.equipment_id], start_date="2026-11-09"),
        "end": payload(world, [other, world.equipment_id], end_date="2026-11-13"),
    }[change]
    collision = world.first.post(URL, json=changed, headers=headers)
    assert collision.status_code == 409
    assert "otros datos" in collision.json()["detail"]
    with app.state.session_factory() as session:
        assert len(session.scalars(select(Reservation)).all()) == 2
        assert len(session.scalars(select(CustomerBookingRequest)).all()) == 1


@pytest.mark.parametrize("original_kind", ["single", "batch"])
def test_single_and_batch_share_the_customer_key_namespace(
    app: FastAPI, customer_world: CustomerWorld, second_unit: int, original_kind: str
) -> None:
    world = customer_world
    headers = intent()
    batch_body = payload(world, [world.equipment_id])
    first_url = SINGLE_URL if original_kind == "single" else URL
    first_body = world.payload() if original_kind == "single" else batch_body
    next_url = URL if original_kind == "single" else SINGLE_URL
    next_body = batch_body if original_kind == "single" else world.payload()
    assert world.first.post(first_url, json=first_body, headers=headers).status_code == 201
    response = world.first.post(next_url, json=next_body, headers=headers)
    assert response.status_code == 409
    assert "otros datos" in response.json()["detail"]
    with app.state.session_factory() as session:
        assert len(session.scalars(select(Reservation)).all()) == 1
        assert len(session.scalars(select(CustomerBookingRequest)).all()) == 1
        assert session.scalars(select(Reservation)).one().equipment_id != second_unit


def test_batch_key_is_scoped_to_customer_even_when_other_customer_uses_it_for_single(
    customer_world: CustomerWorld, second_unit: int
) -> None:
    world = customer_world
    headers = intent()
    batch = world.first.post(URL, json=payload(world, [world.equipment_id]), headers=headers)
    single = world.second.post(SINGLE_URL, json=world.payload(), headers=headers)
    assert batch.status_code == single.status_code == 201
    assert batch.json()[0]["id"] != single.json()["id"]
    assert single.json()["equipment_id"] == second_unit
    assert world.first.get(SINGLE_URL).json() == batch.json()
    assert world.second.get(SINGLE_URL).json() == [single.json()]


def test_failed_batch_rolls_back_reservations_and_intent_then_same_key_can_succeed(
    app: FastAPI, customer_world: CustomerWorld
) -> None:
    world = customer_world
    other = other_model(world)
    occupied = world.create(world.second, equipment_id=other)
    headers = intent()
    body = payload(world, [world.equipment_id, other])
    response = world.first.post(URL, json=body, headers=headers)
    assert response.status_code == 409
    assert world.first.get(SINGLE_URL).json() == []
    with app.state.session_factory() as session:
        assert len(session.scalars(select(Reservation)).all()) == 1
        assert session.scalars(select(CustomerBookingRequest)).all() == []
        assert session.scalars(select(BookingRequestReservation)).all() == []
    assert world.second.post(f"{SINGLE_URL}/{occupied['id']}/cancel").status_code == 200
    created = world.first.post(URL, json=body, headers=headers)
    assert created.status_code == 201, created.text
    assert world.first.post(URL, json=body, headers=headers).json() == created.json()
    with app.state.session_factory() as session:
        assert len(session.scalars(select(Reservation)).all()) == 3
        assert len(session.scalars(select(CustomerBookingRequest)).all()) == 1
        assert len(session.scalars(select(BookingRequestReservation)).all()) == 2


def test_batch_idempotency_header_is_validated_and_still_requires_csrf(
    customer_world: CustomerWorld,
) -> None:
    world = customer_world
    body = payload(world, [world.equipment_id])
    assert (
        world.first.post(URL, json=body, headers={"Idempotency-Key": "invalid"}).status_code == 422
    )
    assert (
        world.first.post(URL, json=body, headers={**intent(), "X-CSRF-Token": "wrong"}).status_code
        == 403
    )
    assert world.first.get(SINGLE_URL).json() == []
