from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import select, text

from rentalab.auth.models import User
from rentalab.catalogue_demo import (
    BOOKING_EQUIPMENT_CODES,
    CATALOGUE_EQUIPMENT,
    seed_catalogue_demo,
)
from rentalab.config import Settings
from rentalab.demo import DEMO_ACCOUNTS, seed_demo
from rentalab.equipment.models import Equipment
from rentalab.equipment.repository import EquipmentRepository
from rentalab.equipment.service import EquipmentService
from rentalab.reservations.models import Reservation
from rentalab.reservations.repository import ReservationRepository
from rentalab.reservations.schemas import DateRange, ReservationCreate
from rentalab.reservations.service import ReservationService

BASE_DATE = date(2040, 3, 1)
CATALOGUE_REFERENCES = tuple(f"RENTALAB-CATALOGUE-{number:02d}" for number in range(1, 11))


def load_existing_demo(settings: Settings) -> None:
    seed_demo(settings, base_date=BASE_DATE, today=lambda: BASE_DATE)


def load_catalogue(settings: Settings, *, base_date: date | None = None):
    return seed_catalogue_demo(settings, base_date=base_date, today=lambda: BASE_DATE)


def business_snapshot(app: FastAPI) -> dict[str, list[tuple]]:
    with app.state.session_factory() as session:
        return {
            table: list(session.execute(text(f"SELECT * FROM {table} ORDER BY id")).tuples())
            for table in ("users", "equipment", "reservations", "incidents")
        }


def test_catalogue_adds_twenty_photographed_units_and_ten_owned_reservations(
    app: FastAPI, settings: Settings
) -> None:
    load_existing_demo(settings)
    before = business_snapshot(app)
    result = load_catalogue(settings)
    assert result.equipment_created == 20
    assert result.reservations_created == 10
    assert result.reservations_existing == 0
    assert result.skipped == ()
    assert len(CATALOGUE_EQUIPMENT) == 20
    assert len({item.code for item in CATALOGUE_EQUIPMENT}) == 20
    assert len(BOOKING_EQUIPMENT_CODES) == len(set(BOOKING_EQUIPMENT_CODES)) == 10

    with app.state.session_factory() as session:
        units = session.scalars(select(Equipment).order_by(Equipment.id)).all()
        assert len(units) == 24
        added = {
            unit.code: unit
            for unit in units
            if unit.code in {item.code for item in CATALOGUE_EQUIPMENT}
        }
        assert len(added) == 20
        assert set(BOOKING_EQUIPMENT_CODES) <= added.keys()
        for definition in CATALOGUE_EQUIPMENT:
            unit = added[definition.code]
            assert unit.active
            assert unit.image_url and unit.image_url.startswith("/api/public/images/")
            assert unit.public_description
            assert unit.technical_specs

        users = session.scalars(select(User)).all()
        assert len(users) == 6
        by_id = {user.id: user for user in users}
        customer_emails = {account.email for account in DEMO_ACCOUNTS[1:5]}
        bookings = session.scalars(
            select(Reservation).where(Reservation.external_reference.in_(CATALOGUE_REFERENCES))
        ).all()
        assert len(bookings) == 10
        assert {booking.equipment_id for booking in bookings} == {
            added[code].id for code in BOOKING_EQUIPMENT_CODES
        }
        assert {booking.customer_email for booking in bookings} == customer_emails
        for booking in bookings:
            owner = by_id[booking.customer_user_id]
            assert owner.role == "customer" and owner.active
            assert booking.customer_name == owner.name
            assert booking.customer_email == owner.email
            assert booking.customer_email in customer_emails
            assert booking.status == "confirmed"
            assert (
                BASE_DATE <= booking.start_date < booking.end_date <= BASE_DATE + timedelta(days=14)
            )
        assert len({(booking.start_date, booking.end_date) for booking in bookings}) > 1
        assert len(session.scalars(select(Reservation)).all()) == 16
        assert not session.scalars(
            select(Reservation).where(Reservation.customer_email == DEMO_ACCOUNTS[-1].email)
        ).all()
        occupied = [
            (
                booking.equipment_id,
                DateRange(start_date=booking.start_date, end_date=booking.end_date),
            )
            for booking in bookings
        ]
        free_ids = {unit.id for unit in added.values()} - {item[0] for item in occupied}

    after = business_snapshot(app)
    assert after["users"] == before["users"]
    assert after["incidents"] == before["incidents"]
    assert after["equipment"][:4] == before["equipment"]
    assert after["reservations"][:6] == before["reservations"]
    with app.state.session_factory() as session:
        service = ReservationService(ReservationRepository(session))
        for equipment_id, dates in occupied:
            assert not service.availability(equipment_id, dates).available
        whole_period = DateRange(start_date=BASE_DATE, end_date=BASE_DATE + timedelta(days=14))
        for equipment_id in free_ids:
            assert service.availability(equipment_id, whole_period).available


def test_rerun_preserves_edited_products_customer_profiles_and_cancelled_reservations(
    app: FastAPI, settings: Settings
) -> None:
    load_existing_demo(settings)
    load_catalogue(settings)
    with app.state.session_factory() as session, session.begin():
        unit = session.scalar(select(Equipment).where(Equipment.code == BOOKING_EQUIPMENT_CODES[0]))
        assert unit is not None
        unit.name = "Unidad editada por administración"
        unit.active = False
        unit.image_url = None
        unit.technical_specs = {"Estado": "Revisado"}
        booking = session.scalar(
            select(Reservation).where(Reservation.external_reference == CATALOGUE_REFERENCES[0])
        )
        assert booking is not None
        booking.status = "cancelled"
        booking.start_date += timedelta(days=100)
        booking.end_date += timedelta(days=100)
        owner = session.get(User, booking.customer_user_id)
        owner.name = "Cliente con perfil actualizado"
    before = business_snapshot(app)
    result = load_catalogue(settings, base_date=BASE_DATE + timedelta(days=365))
    assert result.equipment_created == 0
    assert result.reservations_created == 0
    assert result.reservations_existing == 10
    assert result.skipped == ()
    assert business_snapshot(app) == before


def test_existing_conflict_is_reported_without_overwriting_the_reservation(
    app: FastAPI, settings: Settings
) -> None:
    load_existing_demo(settings)
    definition = next(
        item for item in CATALOGUE_EQUIPMENT if item.code == BOOKING_EQUIPMENT_CODES[0]
    )
    with app.state.session_factory() as session:
        equipment = EquipmentService(EquipmentRepository(session)).create(definition)
        equipment_id = equipment.id
    with app.state.session_factory() as session:
        reservation = ReservationService(ReservationRepository(session)).create(
            ReservationCreate(
                equipment_id=equipment_id,
                customer_name="Reserva anterior",
                customer_email="existing@example.test",
                start_date=BASE_DATE,
                end_date=BASE_DATE + timedelta(days=15),
                external_reference="EXISTING-CATALOGUE-CONFLICT",
            )
        )
        reservation_id = reservation.id
    before = business_snapshot(app)
    result = load_catalogue(settings)
    assert result.equipment_created == 19
    assert result.reservations_created == 9
    assert result.reservations_existing == 0
    assert len(result.skipped) == 1
    after = business_snapshot(app)
    assert after["users"] == before["users"]
    assert after["equipment"][:5] == before["equipment"]
    assert after["reservations"][:7] == before["reservations"]
    with app.state.session_factory() as session:
        unchanged = session.get(Reservation, reservation_id)
        assert unchanged.external_reference == "EXISTING-CATALOGUE-CONFLICT"
        assert unchanged.status == "confirmed"
        assert len(session.scalars(select(Reservation)).all()) == 16
        assert not session.scalars(
            select(Reservation).where(
                Reservation.equipment_id == equipment_id,
                Reservation.external_reference.in_(CATALOGUE_REFERENCES),
            )
        ).all()


def test_missing_customers_fail_without_creating_any_business_records(
    app: FastAPI, settings: Settings
) -> None:
    before = business_snapshot(app)
    with pytest.raises(ValueError):
        load_catalogue(settings)
    assert business_snapshot(app) == before


@pytest.mark.parametrize("role,active", [("admin", True), ("customer", False)])
def test_no_eligible_customers_fails_before_adding_products(
    app: FastAPI, settings: Settings, role: str, active: bool
) -> None:
    load_existing_demo(settings)
    with app.state.session_factory() as session, session.begin():
        customers = session.scalars(select(User).where(User.role == "customer")).all()
        assert len(customers) == 5
        for user in customers:
            user.role = role
            user.active = active
    before = business_snapshot(app)
    with pytest.raises(ValueError):
        load_catalogue(settings)
    assert business_snapshot(app) == before


@pytest.mark.parametrize("customer_count", [1, 2])
def test_one_or_two_existing_active_customers_are_enough_without_new_accounts(
    app: FastAPI, settings: Settings, customer_count: int
) -> None:
    load_existing_demo(settings)
    with app.state.session_factory() as session, session.begin():
        customers = session.scalars(
            select(User).where(User.role == "customer").order_by(User.id)
        ).all()
        selected_ids = {user.id for user in customers[:customer_count]}
        for user in customers[customer_count:]:
            user.active = False
    before_users = business_snapshot(app)["users"]
    result = load_catalogue(settings)
    assert result.equipment_created == 20
    assert result.reservations_created == 10
    assert result.reservations_existing == 0
    assert result.skipped == ()
    assert business_snapshot(app)["users"] == before_users
    with app.state.session_factory() as session:
        bookings = session.scalars(
            select(Reservation).where(Reservation.external_reference.in_(CATALOGUE_REFERENCES))
        ).all()
        assert len(bookings) == 10
        assert {booking.customer_user_id for booking in bookings} == selected_ids
        for booking in bookings:
            owner = session.get(User, booking.customer_user_id)
            assert owner.active and owner.role == "customer"
            assert booking.customer_name == owner.name
            assert booking.customer_email == owner.email
            assert booking.status == "confirmed"


@pytest.mark.parametrize(
    "environment,base_date",
    [("production", BASE_DATE), ("test", BASE_DATE - timedelta(days=1))],
)
def test_production_and_past_dates_fail_before_opening_the_database(
    tmp_path: Path, environment: str, base_date: date
) -> None:
    database_file = tmp_path / "never-created.sqlite3"
    settings = Settings(
        database_url=f"sqlite:///{database_file.as_posix()}", environment=environment
    )
    with pytest.raises(ValueError):
        load_catalogue(settings, base_date=base_date)
    assert not database_file.exists()
