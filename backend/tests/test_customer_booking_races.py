"""Real authenticated HTTP races against independently migrated SQLite files on disk."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from time import monotonic

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.engine import make_url
from test_me_reservations import TODAY, CustomerWorld, login_customer
from test_me_reservations import customer_world as customer_world

from rentalab.clock import get_today_provider
from rentalab.config import Settings
from rentalab.main import create_app
from rentalab.reservations.models import Reservation


@pytest.mark.parametrize("round_number", range(1, 6))
@pytest.mark.parametrize("different_units", [False, True], ids=["same-unit", "distinct-units"])
def test_synchronized_customer_race_has_only_compatible_persisted_reservations(
    app: FastAPI,
    settings: Settings,
    customer_world: CustomerWorld,
    round_number: int,
    different_units: bool,
) -> None:
    world = customer_world
    # Each parametrized round gets its own tmp_path, real migrations, users and sessions.
    database_file = make_url(settings.database_url).database
    assert database_file is not None and database_file != ":memory:"
    assert Path(database_file).is_file()
    other_id = world.equipment_id
    if different_units:
        same_model = world.admin.get(f"/api/equipment/{world.equipment_id}").json()
        same_model = {key: value for key, value in same_model.items() if key != "id"}
        same_model["code"] = f"CAM-TWIN-{round_number}"
        response = world.admin.post("/api/equipment", json=same_model)
        assert response.status_code == 201, response.text
        other_id = response.json()["id"]

    second_app = create_app(settings)
    second_app.dependency_overrides[get_today_provider] = lambda: lambda: TODAY
    launch = Barrier(3)
    attempted = [Event(), Event()]
    connections: list[set[int]] = [set(), set()]
    acquired: list[int] = []
    engines = [app.state.engine, second_app.state.engine]
    listeners = []

    def install_observers(index: int) -> None:
        def checkout(connection, _record, _proxy):
            connections[index].add(id(connection))

        def before(_connection, _cursor, statement, _parameters, _context, _executemany):
            if statement.strip().upper() == "BEGIN IMMEDIATE":
                attempted[index].set()

        def after(_connection, _cursor, statement, _parameters, _context, _executemany):
            if statement.strip().upper() == "BEGIN IMMEDIATE":
                acquired.append(index)
                # The winner holds SQLite's real writer lock until both connections
                # have attempted BEGIN, so this cannot silently become a sequential test.
                assert attempted[1 - index].wait(timeout=5), "Peer never competed for SQLite"

        for name, callback in (
            ("checkout", checkout),
            ("before_cursor_execute", before),
            ("after_cursor_execute", after),
        ):
            event.listen(engines[index], name, callback)
            listeners.append((engines[index], name, callback))

    def submit(browser: TestClient, equipment_id: int):
        launch.wait(timeout=5)
        return browser.post("/api/me/reservations", json=world.payload(equipment_id=equipment_id))

    try:
        with TestClient(second_app) as other:
            login_customer(other, "bruno@example.test")
            for browser, equipment_id in ((world.first, world.equipment_id), (other, other_id)):
                available = browser.get(
                    f"/api/public/equipment/{equipment_id}/availability",
                    params={
                        key: value
                        for key, value in world.payload().items()
                        if key != "equipment_id"
                    },
                )
                assert available.status_code == 200
                assert available.json()["available"] is True
            install_observers(0)
            install_observers(1)
            try:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    first = executor.submit(submit, world.first, world.equipment_id)
                    second = executor.submit(submit, other, other_id)
                    launch.wait(timeout=5)
                    responses = [first.result(timeout=10), second.result(timeout=10)]
            finally:
                for engine, name, callback in listeners:
                    event.remove(engine, name, callback)
            assert all(item.is_set() for item in attempted)
            assert len(acquired) == 2
            assert connections[0] and connections[1]
            assert connections[0].isdisjoint(connections[1])
            assert sorted(response.status_code for response in responses) == (
                [201, 201] if different_units else [201, 409]
            )
            if not different_units:
                conflict = next(response for response in responses if response.status_code == 409)
                assert "consulta la disponibilidad" in conflict.json()["detail"]
                assert "retry-after" not in conflict.headers
                assert "alicia@example.test" not in conflict.text
                assert "bruno@example.test" not in conflict.text

            with app.state.session_factory() as session:
                persisted = session.scalars(select(Reservation)).all()
                assert len(persisted) == (2 if different_units else 1)
                for row in persisted:
                    assert row.status == "confirmed"
                    assert row.origin == "portal"
                    assert row.start_date.isoformat() == "2026-11-10"
                    assert row.end_date.isoformat() == "2026-11-12"
                    owner_index = 0 if row.customer_user_id == world.first_id else 1
                    assert responses[owner_index].status_code == 201
                    assert row.id == responses[owner_index].json()["id"]
                    assert row.customer_user_id == [world.first_id, world.second_id][owner_index]
                assert len({row.equipment_id for row in persisted}) == len(persisted)

            # An identical resend (or a delayed second click) cannot append another row.
            winner = next(
                index for index, response in enumerate(responses) if response.status_code == 201
            )
            resent = [world.first, other][winner].post(
                "/api/me/reservations",
                json=world.payload(equipment_id=[world.equipment_id, other_id][winner]),
            )
            assert resent.status_code == 409
            with app.state.session_factory() as session:
                assert len(session.scalars(select(Reservation)).all()) == len(persisted)
    finally:
        second_app.state.engine.dispose()


@pytest.mark.parametrize("operation", ["create", "cancel"])
@pytest.mark.parametrize("lock_type", ["writer", "reader-commit"])
def test_customer_busy_wait_is_bounded_distinct_from_unavailability_and_can_retry_cleanly(
    app: FastAPI,
    settings: Settings,
    customer_world: CustomerWorld,
    operation: str,
    lock_type: str,
) -> None:
    world = customer_world
    original = world.create() if operation == "cancel" else None
    endpoint = (
        f"/api/me/reservations/{original['id']}/cancel" if original else "/api/me/reservations"
    )
    second_app = create_app(settings.model_copy(update={"sqlite_busy_timeout_ms": 25}))
    second_app.dependency_overrides[get_today_provider] = lambda: lambda: TODAY
    try:
        with TestClient(second_app) as browser:
            login_customer(browser, "alicia@example.test")
            with app.state.engine.connect() as lock_owner:
                if lock_type == "writer":
                    lock_owner.exec_driver_sql("BEGIN IMMEDIATE")
                else:
                    lock_owner.exec_driver_sql("BEGIN")
                    lock_owner.exec_driver_sql("SELECT id FROM equipment").all()
                started = monotonic()
                failed = browser.post(endpoint, json={} if original else world.payload())
                elapsed = monotonic() - started
                assert failed.status_code == 503, failed.text
                assert failed.headers["Retry-After"] == "1"
                assert "ocupada" in failed.json()["detail"]
                assert "disponib" not in failed.json()["detail"]
                assert elapsed < 2, f"25 ms SQLite timeout took {elapsed:.3f} s"
                assert world.first.get("/api/me/reservations").json() == (
                    [original] if original else []
                )
                lock_owner.rollback()
            retried = browser.post(endpoint, json={} if original else world.payload())
            assert retried.status_code == (200 if original else 201), retried.text
            assert retried.json()["status"] == ("cancelled" if original else "confirmed")
            with app.state.session_factory() as session:
                rows = session.scalars(select(Reservation)).all()
                assert len(rows) == 1
                assert rows[0].customer_user_id == world.first_id
                assert rows[0].status == retried.json()["status"]
    finally:
        second_app.state.engine.dispose()
