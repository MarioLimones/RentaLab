"""Explicit local demonstration data; never imported or run by application startup."""

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from rentalab.auth.models import User
from rentalab.auth.schemas import RegisterRequest, UserRole
from rentalab.auth.service import AuthService, DuplicateUserEmail
from rentalab.clock import madrid_today
from rentalab.config import Settings
from rentalab.database import create_database_engine
from rentalab.equipment.models import Equipment
from rentalab.reservations.models import Reservation
from rentalab.reservations.repository import ReservationRepository
from rentalab.reservations.schemas import ReservationCreate
from rentalab.reservations.service import ReservationConflict, ReservationService
from rentalab.seed import seed_equipment


@dataclass(frozen=True)
class DemoAccount:
    name: str
    email: str
    password: str
    role: UserRole = "customer"


# Public, fictional credentials for this opt-in local demonstration only.
# Each account is a real persisted user with an independently hashed password.
DEMO_ACCOUNTS = (
    DemoAccount(
        "Administración Demo",
        "admin.demo@rentalab.example.test",
        "Demo-RentaLab-Admin-2026!",
        "admin",
    ),
    DemoAccount("Alicia Demo", "alicia.demo@rentalab.example.test", "Demo-RentaLab-Alicia-2026!"),
    DemoAccount("Bruno Demo", "bruno.demo@rentalab.example.test", "Demo-RentaLab-Bruno-2026!"),
    DemoAccount("Carla Demo", "carla.demo@rentalab.example.test", "Demo-RentaLab-Carla-2026!"),
    DemoAccount("Diego Demo", "diego.demo@rentalab.example.test", "Demo-RentaLab-Diego-2026!"),
    DemoAccount("Elena Demo", "elena.demo@rentalab.example.test", "Demo-RentaLab-Elena-2026!"),
)


@dataclass(frozen=True)
class DemoBooking:
    reference: str
    account_index: int
    equipment_code: str
    start_offset: int
    end_offset: int
    cancelled: bool = False


# References deliberately do not contain the base date: a later rerun preserves
# the original dates, ownership and status instead of generating another cohort.
DEMO_BOOKINGS = (
    DemoBooking("RENTALAB-DEMO-01", 1, "CAM-001", 7, 10),
    DemoBooking("RENTALAB-DEMO-02", 2, "CAM-001", 10, 13),
    DemoBooking("RENTALAB-DEMO-03", 3, "CAM-002", 7, 11),
    DemoBooking("RENTALAB-DEMO-04", 4, "AUD-001", 3, 5),
    DemoBooking("RENTALAB-DEMO-05", 1, "LGT-001", 15, 17),
    DemoBooking("RENTALAB-DEMO-06", 3, "CAM-001", 20, 22, cancelled=True),
)


@dataclass(frozen=True)
class DemoSeedResult:
    base_date: date
    accounts_created: tuple[str, ...]
    equipment_created: int
    reservations_created: int
    reservations_existing: int
    skipped: tuple[str, ...]


def seed_demo(
    settings: Settings,
    *,
    base_date: date | None = None,
    today: Callable[[], date] = madrid_today,
) -> DemoSeedResult:
    """Add missing demo records, preserving every existing record and password.

    Existing equipment still goes through the same availability check as HTTP
    clients. A conflict is reported, never repaired by changing real data.
    """
    if settings.environment == "production":
        raise ValueError("La carga de demostración está prohibida en production")
    current_day = today()
    base = base_date or current_day
    if base < current_day:
        raise ValueError("La fecha base no puede ser anterior a hoy en Europe/Madrid")
    # Validate the complete date range before making any database changes.
    try:
        ranges = [
            (base + timedelta(days=item.start_offset), base + timedelta(days=item.end_offset))
            for item in DEMO_BOOKINGS
        ]
    except OverflowError:
        raise ValueError(
            "La fecha base no permite calcular los intervalos de demostración"
        ) from None

    engine = create_database_engine(
        settings.database_url, busy_timeout_ms=settings.sqlite_busy_timeout_ms
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    created_accounts: list[str] = []
    skipped: list[str] = []
    reservations_created = reservations_existing = 0
    try:
        auth = AuthService(settings, factory)
        for account in DEMO_ACCOUNTS:
            with factory() as session:
                existing = session.scalar(select(User).where(User.email == account.email))
            if existing is not None:
                if existing.role != account.role or not existing.active:
                    skipped.append(
                        f"{account.email}: la cuenta existente no es {account.role} activa; "
                        "se conservan sus permisos y estado"
                    )
                continue
            try:
                auth.register(
                    RegisterRequest(
                        name=account.name, email=account.email, password=account.password
                    ),
                    role=account.role,
                )
                created_accounts.append(account.email)
            except DuplicateUserEmail:
                # Another explicit invocation may have created it concurrently.
                with factory() as session:
                    existing = session.scalar(select(User).where(User.email == account.email))
                if existing is None:
                    skipped.append(
                        f"{account.email}: el correo coincide con el operador heredado; "
                        "no se ha creado otra identidad"
                    )
                elif existing.role != account.role or not existing.active:
                    skipped.append(
                        f"{account.email}: la cuenta existente no es {account.role} activa; "
                        "se conservan sus permisos y estado"
                    )
        with factory() as session, session.begin():
            equipment_created = seed_equipment(session)

        for booking, (start, end) in zip(DEMO_BOOKINGS, ranges, strict=True):
            account = DEMO_ACCOUNTS[booking.account_index]
            with factory() as session:
                existing = session.scalar(
                    select(Reservation.id).where(
                        Reservation.external_reference == booking.reference
                    )
                )
                if existing is not None:
                    reservations_existing += 1
                    continue
                user = session.scalar(select(User).where(User.email == account.email))
                equipment_id = session.scalar(
                    select(Equipment.id).where(Equipment.code == booking.equipment_code)
                )
                if user is None or not user.active or user.role != "customer":
                    skipped.append(f"{booking.reference}: la cuenta no es un cliente activo")
                    continue
                assert equipment_id is not None
                # Existing profile data remains authoritative, including an edited name.
                data = ReservationCreate(
                    equipment_id=equipment_id,
                    customer_name=user.name,
                    customer_email=user.email,
                    start_date=start,
                    end_date=end,
                    external_reference=booking.reference,
                )
                user_id = user.id
            try:
                with factory() as session:
                    service = ReservationService(ReservationRepository(session))
                    service.create_for_customer(
                        data,
                        customer_user_id=user_id,
                        today=lambda: current_day,
                        initial_status="cancelled" if booking.cancelled else "confirmed",
                    )
                reservations_created += 1
            except ReservationConflict as error:
                skipped.append(f"{booking.reference}: {error}")
        return DemoSeedResult(
            base,
            tuple(created_accounts),
            equipment_created,
            reservations_created,
            reservations_existing,
            tuple(skipped),
        )
    finally:
        engine.dispose()


def iso_date(value: str) -> date:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise argparse.ArgumentTypeError("Usa YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("La fecha no es válida") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Crear datos ficticios locales explícitamente; prohibido en production",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--base-date", type=iso_date, help="Fecha base YYYY-MM-DD; por defecto, hoy en Madrid"
    )
    args = parser.parse_args(argv)
    try:
        result = seed_demo(Settings(), base_date=args.base_date)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "No se pudo completar la carga; comprueba la base y aplica Alembic primero. "
            "Puedes repetirla sin borrar los registros ya creados.",
            file=sys.stderr,
        )
        return 1
    print(
        f"Demostración local; fecha base {result.base_date.isoformat()}. "
        f"Cuentas nuevas: {len(result.accounts_created)}; "
        f"equipos nuevos: {result.equipment_created}; "
        f"reservas nuevas: {result.reservations_created}; "
        f"reservas conservadas: {result.reservations_existing}."
    )
    print("Las cuentas y reservas existentes conservan contraseñas, roles, fechas y estados.")
    for account in DEMO_ACCOUNTS:
        credential = (
            account.password
            if account.email in result.accounts_created
            else "cuenta existente; contraseña conservada"
        )
        print(f"{account.role}: {account.email} | {credential}")
    for reason in result.skipped:
        print(f"Omitida {reason}", file=sys.stderr)
    return 1 if result.skipped else 0


if __name__ == "__main__":
    raise SystemExit(main())
