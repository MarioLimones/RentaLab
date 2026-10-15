import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from conftest import TEST_PASSWORD_HASH
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text

from rentalab.auth.models import User
from rentalab.auth.schemas import RegisterRequest
from rentalab.config import Settings
from rentalab.demo import DEMO_ACCOUNTS, DEMO_BOOKINGS, seed_demo
from rentalab.equipment.models import Equipment
from rentalab.incidents.models import Incident
from rentalab.reservations.models import Reservation
from rentalab.reservations.repository import ReservationRepository
from rentalab.reservations.schemas import DateRange, ReservationCreate
from rentalab.reservations.service import ReservationService
from rentalab.seed import seed_equipment

BASE_DATE = date(2040, 3, 1)


def load_demo(settings: Settings, *, base_date: date = BASE_DATE):
    return seed_demo(settings, base_date=base_date, today=lambda: BASE_DATE)


def business_snapshot(app: FastAPI) -> dict[str, list[tuple]]:
    with app.state.session_factory() as session:
        return {
            table: list(session.execute(text(f"SELECT * FROM {table} ORDER BY id")).tuples())
            for table in ("users", "equipment", "reservations", "incidents")
        }


def test_demo_creates_real_owners_physical_units_adjacent_dates_and_cancelled_history(
    app: FastAPI, settings: Settings
) -> None:
    result = load_demo(settings)
    assert result.accounts_created == tuple(account.email for account in DEMO_ACCOUNTS)
    assert result.equipment_created == 4
    assert result.reservations_created == 6
    assert result.reservations_existing == 0
    assert result.skipped == ()
    with app.state.session_factory() as session:
        users = session.scalars(select(User).order_by(User.id)).all()
        assert len(users) == 6
        assert [user.role for user in users] == ["admin"] + ["customer"] * 5
        assert all(user.active for user in users)
        for user, account in zip(users, DEMO_ACCOUNTS, strict=True):
            assert user.password_hash.startswith("$argon2id$")
            assert PasswordHasher().verify(user.password_hash, account.password)
        units = session.scalars(select(Equipment)).all()
        assert len({unit.code for unit in units}) == 4
        cameras = sorted(
            (unit for unit in units if unit.category == "Cámaras"), key=lambda u: u.code
        )
        assert len(cameras) == 2
        assert cameras[0].name == cameras[1].name
        assert cameras[0].id != cameras[1].id
        bookings = session.scalars(select(Reservation).order_by(Reservation.id)).all()
        assert len(bookings) == 6
        for booking, definition in zip(bookings, DEMO_BOOKINGS, strict=True):
            assert booking.customer_user_id == users[definition.account_index].id
            assert booking.customer_email == users[definition.account_index].email
            assert booking.origin == "portal"
            assert booking.start_date == BASE_DATE + timedelta(days=definition.start_offset)
            assert booking.end_date == BASE_DATE + timedelta(days=definition.end_offset)
            assert booking.status == ("cancelled" if definition.cancelled else "confirmed")
        assert bookings[0].equipment_id == bookings[1].equipment_id
        assert bookings[0].end_date == bookings[1].start_date
        assert bookings[0].equipment_id != bookings[2].equipment_id
        assert bookings[0].start_date == bookings[2].start_date
        assert not any(booking.customer_user_id == users[-1].id for booking in bookings)
        cancelled = bookings[-1]
        dates = DateRange(start_date=cancelled.start_date, end_date=cancelled.end_date)
    with app.state.session_factory() as session:
        assert (
            ReservationService(ReservationRepository(session))
            .availability(cancelled.equipment_id, dates)
            .available
        )


def test_all_six_demo_accounts_authenticate_independently_and_new_customer_has_no_bookings(
    app: FastAPI, settings: Settings
) -> None:
    load_demo(settings)
    session_ids: set[str] = set()
    for account in DEMO_ACCOUNTS:
        with TestClient(app) as browser:
            csrf = browser.get("/api/auth/csrf").json()["csrf_token"]
            login = browser.post(
                "/api/auth/login",
                json={"username": account.email, "password": account.password},
                headers={"X-CSRF-Token": csrf},
            )
            assert login.status_code == 200
            identity = login.json()
            assert identity["role"] == account.role
            assert identity["user"]["email"] == account.email
            session_ids.add(browser.cookies["rentalab_session"])
            if account.role == "customer":
                own = browser.get("/api/me/reservations")
                assert own.status_code == 200
                if account == DEMO_ACCOUNTS[-1]:
                    assert own.json() == []
                else:
                    assert own.json()
                assert browser.get("/api/reservations").status_code == 403
            else:
                assert len(browser.get("/api/reservations").json()) == 6
    assert len(session_ids) == 6


def test_rerun_preserves_all_values_passwords_roles_dates_and_cancellations(
    app: FastAPI, settings: Settings
) -> None:
    load_demo(settings)
    with app.state.session_factory() as session, session.begin():
        user = session.scalar(select(User).where(User.email == DEMO_ACCOUNTS[1].email))
        assert user is not None
        user.name = "Nombre cambiado por la persona"
        user.password_hash = PasswordHasher().hash("changed-local-password")
        unit = session.scalar(select(Equipment).where(Equipment.code == "CAM-001"))
        assert unit is not None
        unit.name = "Unidad editada"
        unit.active = False
        booking = session.scalar(
            select(Reservation).where(Reservation.external_reference == "RENTALAB-DEMO-01")
        )
        assert booking is not None
        booking.status = "cancelled"
        booking.start_date += timedelta(days=100)
        booking.end_date += timedelta(days=100)
    before = business_snapshot(app)
    result = load_demo(settings, base_date=BASE_DATE + timedelta(days=365))
    assert result.accounts_created == ()
    assert result.equipment_created == 0
    assert result.reservations_created == 0
    assert result.reservations_existing == 6
    assert result.skipped == ()
    assert business_snapshot(app) == before


@pytest.mark.parametrize("role,active", [("customer", True), ("admin", False)])
def test_existing_admin_email_is_never_promoted_or_reactivated_silently(
    app: FastAPI, settings: Settings, role: str, active: bool
) -> None:
    account = DEMO_ACCOUNTS[0]
    existing = app.state.auth_service.register(
        RegisterRequest(name="Cuenta anterior", email=account.email, password="existing-password"),
        role=role,
    )
    with app.state.session_factory() as session, session.begin():
        user = session.get(User, existing.id)
        user.active = active
        original_hash = user.password_hash
    result = load_demo(settings)
    assert len(result.accounts_created) == 5
    assert any(account.email in reason for reason in result.skipped)
    with app.state.session_factory() as session:
        user = session.get(User, existing.id)
        assert (user.name, user.role, user.active, user.password_hash) == (
            "Cuenta anterior",
            role,
            active,
            original_hash,
        )


def test_demo_reports_real_reservation_conflict_without_repairing_existing_data(
    app: FastAPI, settings: Settings
) -> None:
    with app.state.session_factory() as session, session.begin():
        seed_equipment(session)
        equipment_id = session.scalar(select(Equipment.id).where(Equipment.code == "CAM-001"))
    with app.state.session_factory() as session:
        reservation = ReservationService(ReservationRepository(session)).create(
            ReservationCreate(
                equipment_id=equipment_id,
                customer_name="Otra reserva preexistente",
                customer_email="other@example.test",
                start_date=BASE_DATE + timedelta(days=7),
                end_date=BASE_DATE + timedelta(days=10),
                external_reference="NOT-DEMO",
            )
        )
        reservation_id = reservation.id
    result = load_demo(settings)
    assert result.reservations_created == 5
    assert len(result.skipped) == 1
    assert "RENTALAB-DEMO-01" in result.skipped[0]
    with app.state.session_factory() as session:
        unchanged = session.get(Reservation, reservation_id)
        assert unchanged.status == "confirmed"
        assert unchanged.customer_name == "Otra reserva preexistente"
        assert unchanged.external_reference == "NOT-DEMO"
        assert len(session.scalars(select(Reservation)).all()) == 6


def test_demo_reports_legacy_operator_email_collision_without_claiming_admin_exists(
    app: FastAPI, settings: Settings
) -> None:
    settings = settings.model_copy(
        update={
            "operator_username": DEMO_ACCOUNTS[0].email,
            "operator_password_hash": SecretStr(TEST_PASSWORD_HASH),
        }
    )
    result = load_demo(settings)
    assert len(result.accounts_created) == 5
    assert len(result.skipped) == 1
    assert "operador heredado" in result.skipped[0]
    with app.state.session_factory() as session:
        assert session.scalar(select(User).where(User.email == DEMO_ACCOUNTS[0].email)) is None
        assert len(session.scalars(select(User)).all()) == 5


@pytest.mark.parametrize("block", ["inactive", "incident"])
def test_demo_obeys_shared_inactive_and_blocking_incident_rules(
    app: FastAPI, settings: Settings, block: str
) -> None:
    with app.state.session_factory() as session, session.begin():
        seed_equipment(session)
        unit = session.scalar(select(Equipment).where(Equipment.code == "CAM-001"))
        if block == "inactive":
            unit.active = False
        else:
            session.add(Incident(equipment_id=unit.id, title="No alquilar", blocking=True))
        unit_id = unit.id
    result = load_demo(settings)
    assert result.reservations_created == 3
    assert len(result.skipped) == 3
    with app.state.session_factory() as session:
        assert not session.scalars(
            select(Reservation).where(Reservation.equipment_id == unit_id)
        ).all()
        if block == "inactive":
            assert not session.get(Equipment, unit_id).active
        else:
            assert session.scalar(select(Incident)).blocking


@pytest.mark.parametrize("base", [BASE_DATE - timedelta(days=1), date.max])
def test_invalid_base_dates_fail_before_opening_or_changing_database(
    tmp_path: Path, base: date
) -> None:
    database_file = tmp_path / "never-created.sqlite3"
    settings = Settings(database_url=f"sqlite:///{database_file.as_posix()}", environment="test")
    with pytest.raises(ValueError):
        load_demo(settings, base_date=base)
    assert not database_file.exists()


def test_explicit_cli_refuses_production_without_opening_database(tmp_path: Path) -> None:
    database_file = tmp_path / "never-created.sqlite3"
    environment = {
        **os.environ,
        "RENTALAB_ENVIRONMENT": "production",
        "RENTALAB_DATABASE_URL": f"sqlite:///{database_file.as_posix()}",
    }
    result = subprocess.run(
        [sys.executable, "-m", "rentalab.demo"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 1
    assert "prohibida en production" in result.stderr
    assert "Demo-RentaLab" not in result.stdout
    assert not database_file.exists()
