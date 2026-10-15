"""A repeated single-booking intent never consumes another unit after a lost response."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, select, text
from test_me_reservations import TODAY, CustomerWorld, login_customer
from test_me_reservations import customer_world as customer_world
from test_product_reservations import second_unit as second_unit

from alembic import command
from rentalab.clock import get_today_provider
from rentalab.config import Settings
from rentalab.database import create_database_engine
from rentalab.main import create_app
from rentalab.reservations.models import (
    BookingRequestReservation,
    CustomerBookingRequest,
    Reservation,
)

URL = "/api/me/reservations"


def intent() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


def test_lost_response_retry_after_restart_returns_original_without_consuming_second_unit(
    app: FastAPI, settings: Settings, customer_world: CustomerWorld, second_unit: int
) -> None:
    world = customer_world
    headers = intent()
    original = world.first.post(URL, json=world.payload(), headers=headers)
    assert original.status_code == 201, original.text
    # The first client can lose the result after commit. A new app/session must recover
    # it from SQLite rather than an in-memory cache or whichever physical unit is free.
    recreated = create_app(settings)
    recreated.dependency_overrides[get_today_provider] = lambda: lambda: TODAY
    try:
        with TestClient(recreated) as browser:
            login_customer(browser, "alicia@example.test")
            recovered = browser.post(URL, json=world.payload(), headers=headers)
            assert recovered.status_code == 201, recovered.text
            assert recovered.json() == original.json()
            assert recovered.headers["location"] == original.headers["location"]
            assert set(recovered.json()) == {
                "id",
                "equipment_id",
                "start_date",
                "end_date",
                "status",
            }
            assert headers["Idempotency-Key"] not in recovered.text
        with app.state.session_factory() as session:
            bookings = session.scalars(select(Reservation)).all()
            requests = session.scalars(select(CustomerBookingRequest)).all()
            assert len(bookings) == len(requests) == 1
            assert bookings[0].equipment_id == world.equipment_id
            assert requests[0].items[0].requested_equipment_id == world.equipment_id
        assert second_unit != original.json()["equipment_id"]
    finally:
        recreated.state.engine.dispose()


def test_original_requested_model_is_retained_when_another_physical_unit_is_allocated(
    app: FastAPI, customer_world: CustomerWorld, second_unit: int
) -> None:
    world = customer_world
    world.create(world.second)
    headers = intent()
    response = world.first.post(URL, json=world.payload(), headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["equipment_id"] == second_unit
    replay = world.first.post(URL, json=world.payload(), headers=headers)
    assert replay.status_code == 201
    assert replay.json() == response.json()
    # A different URL-level product/alias is a different payload even for the same model.
    collision = world.first.post(URL, json=world.payload(equipment_id=second_unit), headers=headers)
    assert collision.status_code == 409
    with app.state.session_factory() as session:
        request = session.scalars(select(CustomerBookingRequest)).one()
        assert request.items[0].requested_equipment_id == world.equipment_id
        assert request.items[0].reservation_id == response.json()["id"]


@pytest.mark.parametrize("changes", [{"start_date": "2026-11-09"}, {"end_date": "2026-11-13"}])
def test_reusing_customer_key_with_other_dates_is_a_conflict_without_extra_writes(
    app: FastAPI, customer_world: CustomerWorld, changes: dict[str, str]
) -> None:
    world = customer_world
    headers = intent()
    original = world.first.post(URL, json=world.payload(), headers=headers)
    assert original.status_code == 201
    response = world.first.post(URL, json=world.payload(**changes), headers=headers)
    assert response.status_code == 409
    assert "otros datos" in response.json()["detail"]
    assert world.first.get(URL).json() == [original.json()]
    with app.state.session_factory() as session:
        assert len(session.scalars(select(CustomerBookingRequest)).all()) == 1


def test_key_is_scoped_to_authenticated_customer_and_new_keys_remain_independent(
    app: FastAPI, customer_world: CustomerWorld, second_unit: int
) -> None:
    world = customer_world
    headers = intent()
    first = world.first.post(URL, json=world.payload(), headers=headers)
    second = world.second.post(URL, json=world.payload(), headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert second.json()["equipment_id"] == second_unit
    for browser, expected in ((world.first, first), (world.second, second)):
        replay = browser.post(URL, json=world.payload(), headers=headers)
        assert replay.status_code == 201
        assert replay.json() == expected.json()
        assert browser.get(URL).json() == [expected.json()]
    assert world.first.get(f"{URL}/{second.json()['id']}").status_code == 404
    with app.state.session_factory() as session:
        assert len(session.scalars(select(CustomerBookingRequest)).all()) == 2


def test_explicit_new_key_can_create_a_separate_booking_when_another_unit_is_free(
    customer_world: CustomerWorld, second_unit: int
) -> None:
    world = customer_world
    first = world.first.post(URL, json=world.payload(), headers=intent())
    second = world.first.post(URL, json=world.payload(), headers=intent())
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert second.json()["equipment_id"] == second_unit


def test_requests_without_key_keep_legacy_behavior_and_do_not_create_intent_records(
    app: FastAPI, customer_world: CustomerWorld, second_unit: int
) -> None:
    world = customer_world
    first = world.first.post(URL, json=world.payload())
    second = world.first.post(URL, json=world.payload())
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert second.json()["equipment_id"] == second_unit
    with app.state.session_factory() as session:
        assert session.scalars(select(CustomerBookingRequest)).all() == []


def test_replay_preserves_current_cancelled_state_even_after_start_and_deactivation(
    app: FastAPI, customer_world: CustomerWorld
) -> None:
    world = customer_world
    headers = intent()
    original = world.first.post(URL, json=world.payload(), headers=headers)
    assert original.status_code == 201
    cancelled = world.first.post(f"{URL}/{original.json()['id']}/cancel")
    assert cancelled.status_code == 200
    inactive = world.admin.patch(f"/api/equipment/{world.equipment_id}", json={"active": False})
    assert inactive.status_code == 200
    app.dependency_overrides[get_today_provider] = lambda: lambda: date(2026, 12, 1)
    replay = world.first.post(URL, json=world.payload(), headers=headers)
    assert replay.status_code == 201, replay.text
    assert replay.json() == cancelled.json()
    assert world.first.get(URL).json() == [cancelled.json()]


def test_rejected_attempt_does_not_consume_key_and_later_retry_can_succeed(
    app: FastAPI, customer_world: CustomerWorld
) -> None:
    world = customer_world
    occupied = world.create(world.second)
    headers = intent()
    assert world.first.post(URL, json=world.payload(), headers=headers).status_code == 409
    with app.state.session_factory() as session:
        assert session.scalars(select(CustomerBookingRequest)).all() == []
    assert world.second.post(f"{URL}/{occupied['id']}/cancel").status_code == 200
    response = world.first.post(URL, json=world.payload(), headers=headers)
    assert response.status_code == 201, response.text
    assert world.first.post(URL, json=world.payload(), headers=headers).json() == response.json()


@pytest.mark.parametrize(
    "key", ["", "not-a-uuid", "x" * 100, "00000000-0000-0000-0000-00000000000z"]
)
def test_invalid_idempotency_header_is_422_without_creating_records(
    app: FastAPI, customer_world: CustomerWorld, key: str
) -> None:
    world = customer_world
    response = world.first.post(URL, json=world.payload(), headers={"Idempotency-Key": key})
    assert response.status_code == 422
    assert world.first.get(URL).json() == []
    with app.state.session_factory() as session:
        assert session.scalars(select(CustomerBookingRequest)).all() == []


def test_header_does_not_replace_authentication_authorization_or_csrf(
    app: FastAPI, customer_world: CustomerWorld
) -> None:
    world = customer_world
    headers = intent()
    with TestClient(app) as visitor:
        assert visitor.post(URL, json=world.payload(), headers=headers).status_code == 401
    assert world.admin.post(URL, json=world.payload(), headers=headers).status_code == 403
    assert (
        world.first.post(
            URL, json=world.payload(), headers={**headers, "X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
    assert world.first.get(URL).json() == []


@pytest.mark.parametrize("operation", ["single", "batch_one", "batch_multiple"])
def test_concurrent_same_customer_intents_share_original_reservations_across_apps(
    app: FastAPI,
    settings: Settings,
    customer_world: CustomerWorld,
    second_unit: int,
    operation: str,
) -> None:
    world = customer_world
    requested_ids = [world.equipment_id]
    if operation == "batch_multiple":
        for index in range(2):
            equipment = world.admin.post(
                "/api/equipment",
                json={"code": f"OTHER-{index}", "name": "Otro modelo", "category": "Audio"},
            )
            assert equipment.status_code == 201
            if index == 0:
                requested_ids.insert(0, equipment.json()["id"])
    url = URL if operation == "single" else f"{URL}/batch"
    payload = (
        world.payload()
        if operation == "single"
        else {
            "equipment_ids": requested_ids,
            "start_date": world.payload()["start_date"],
            "end_date": world.payload()["end_date"],
        }
    )
    other_app = create_app(settings)
    other_app.dependency_overrides[get_today_provider] = lambda: lambda: TODAY
    first_has_lock = Event()
    second_attempted = Event()
    headers = intent()

    def hold_first(_connection, _cursor, statement, *_args):
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            first_has_lock.set()
            assert second_attempted.wait(timeout=5), "Second request did not attempt its write"

    def observe_second(_connection, _cursor, statement, *_args):
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            second_attempted.set()

    try:
        with TestClient(other_app) as browser:
            login_customer(browser, "alicia@example.test")
            event.listen(app.state.engine, "after_cursor_execute", hold_first)
            event.listen(other_app.state.engine, "before_cursor_execute", observe_second)
            try:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    first = executor.submit(world.first.post, url, json=payload, headers=headers)
                    assert first_has_lock.wait(timeout=5)
                    second = executor.submit(browser.post, url, json=payload, headers=headers)
                    responses = [first.result(timeout=10), second.result(timeout=10)]
            finally:
                event.remove(app.state.engine, "after_cursor_execute", hold_first)
                event.remove(other_app.state.engine, "before_cursor_execute", observe_second)
        assert [response.status_code for response in responses] == [201, 201]
        assert responses[0].json() == responses[1].json()
        with app.state.session_factory() as session:
            assert len(session.scalars(select(Reservation)).all()) == len(requested_ids)
            assert len(session.scalars(select(CustomerBookingRequest)).all()) == 1
            assert len(session.scalars(select(BookingRequestReservation)).all()) == len(
                requested_ids
            )
        result = responses[0].json()
        rows = [result] if isinstance(result, dict) else result
        assert [row["equipment_id"] for row in rows] == requested_ids
        assert all(row["equipment_id"] != second_unit for row in rows)
    finally:
        other_app.state.engine.dispose()


def test_booking_request_migration_preserves_existing_data_and_reverses_cleanly(
    tmp_path: Path,
) -> None:
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    database_url = f"sqlite:///{(tmp_path / 'booking-requests-migration.sqlite3').as_posix()}"
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_database_engine(database_url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0010_saved_products")
            for statement in (
                "INSERT INTO users (id,name,email,password_hash,role,active) "
                "VALUES (7,'Cliente previo','previous@example.test','test-hash','customer',1)",
                "INSERT INTO equipment (id,code,name,category,description,active) "
                "VALUES (41,'OLD-CAM','Equipo previo','Cámaras','Nota interna',0)",
                "INSERT INTO reservations (id,equipment_id,customer_user_id,customer_name,"
                "customer_email,start_date,end_date,status,external_reference,origin) "
                "VALUES (52,41,7,'Cliente previo','previous@example.test','2026-11-10',"
                "'2026-11-12','confirmed','HISTORICAL','portal')",
                "INSERT INTO incidents (id,equipment_id,author_user_id,title,description,"
                "blocking,status,resolution,reservation_id) "
                "VALUES (63,41,7,'Aviso previo','Prueba',0,'resolved','Reparada',52)",
                "INSERT INTO saved_products (customer_user_id,equipment_id) VALUES (7,41)",
            ):
                connection.execute(text(statement))
            tables = ("users", "equipment", "reservations", "incidents", "saved_products")

            def snapshot() -> dict:
                return {
                    table: list(connection.execute(text(f"SELECT * FROM {table}")).mappings())
                    for table in tables
                }

            before = snapshot()
            command.upgrade(config, "head")
            assert snapshot() == before
            assert connection.execute(text("SELECT * FROM booking_requests")).all() == []
            assert (
                connection.execute(text("SELECT * FROM booking_request_reservations")).all() == []
            )
            connection.execute(
                text(
                    "INSERT INTO booking_requests (customer_user_id,idempotency_key,"
                    "operation,start_date,end_date) "
                    "VALUES (7,:key,'single','2026-11-10','2026-11-12')"
                ),
                {"key": "49917cb0-8d1a-4d8c-aa46-59959a7e797a"},
            )
            connection.execute(
                text(
                    "INSERT INTO booking_request_reservations (customer_user_id,idempotency_key,"
                    "position,requested_equipment_id,reservation_id) VALUES (7,:key,0,41,52)"
                ),
                {"key": "49917cb0-8d1a-4d8c-aa46-59959a7e797a"},
            )
            assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
            command.check(config)
            command.downgrade(config, "0010_saved_products")
            assert not inspect(connection).has_table("booking_requests")
            assert not inspect(connection).has_table("booking_request_reservations")
            assert snapshot() == before
            command.upgrade(config, "head")
            assert connection.execute(text("SELECT * FROM booking_requests")).all() == []
            assert snapshot() == before
    finally:
        engine.dispose()
