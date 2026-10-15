from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rentalab.database import immediate_transaction
from rentalab.equipment.models import Equipment
from rentalab.incidents.models import Incident
from rentalab.reservations.models import (
    BookingRequestReservation,
    CustomerBookingRequest,
    Reservation,
)
from rentalab.reservations.schemas import ReservationFilters


class ReservationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def write_transaction(self) -> AbstractContextManager[None]:
        return immediate_transaction(self.session)

    def has_blocking_incident(self, equipment_id: int) -> bool:
        return (
            self.session.scalar(
                select(Incident.id)
                .where(
                    Incident.equipment_id == equipment_id,
                    Incident.blocking.is_(True),
                    Incident.status.in_(("open", "in_progress")),
                )
                .limit(1)
            )
            is not None
        )

    def get_equipment(self, equipment_id: int) -> Equipment | None:
        return self.session.get(Equipment, equipment_id)

    def get_equipment_by_code(self, code: str) -> Equipment | None:
        return self.session.scalar(select(Equipment).where(Equipment.code == code))

    def get_by_reference(self, reference: str) -> Reservation | None:
        return self.session.scalar(
            select(Reservation).where(Reservation.external_reference == reference)
        )

    def get(self, reservation_id: int) -> Reservation | None:
        return self.session.get(Reservation, reservation_id)

    def get_for_customer(self, reservation_id: int, customer_user_id: int) -> Reservation | None:
        return self.session.scalar(
            select(Reservation).where(
                Reservation.id == reservation_id,
                Reservation.customer_user_id == customer_user_id,
            )
        )

    def get_booking_request(
        self, customer_user_id: int, idempotency_key: str
    ) -> CustomerBookingRequest | None:
        return self.session.get(CustomerBookingRequest, (customer_user_id, idempotency_key))

    def add_booking_request(self, request: CustomerBookingRequest) -> None:
        self.session.add(request)

    def reservations_for_booking_request(
        self, customer_user_id: int, idempotency_key: str
    ) -> list[Reservation]:
        return list(
            self.session.scalars(
                select(Reservation)
                .join(
                    BookingRequestReservation,
                    BookingRequestReservation.reservation_id == Reservation.id,
                )
                .where(
                    BookingRequestReservation.customer_user_id == customer_user_id,
                    BookingRequestReservation.idempotency_key == idempotency_key,
                    Reservation.customer_user_id == customer_user_id,
                )
                .order_by(BookingRequestReservation.position)
            )
        )

    def list_for_customer(self, customer_user_id: int) -> Sequence[Reservation]:
        return self.session.scalars(
            select(Reservation)
            .where(Reservation.customer_user_id == customer_user_id)
            .order_by(Reservation.start_date, Reservation.id)
        ).all()

    def list(self, filters: ReservationFilters) -> Sequence[Reservation]:
        statement = select(Reservation).order_by(Reservation.start_date, Reservation.id)
        if filters.equipment_id is not None:
            statement = statement.where(Reservation.equipment_id == filters.equipment_id)
        if filters.status is not None:
            statement = statement.where(Reservation.status == filters.status)
        if filters.customer_user_id is not None:
            statement = statement.where(Reservation.customer_user_id == filters.customer_user_id)
        if filters.origin is not None:
            statement = statement.where(Reservation.origin == filters.origin)
        if filters.start_date is not None and filters.end_date is not None:
            statement = statement.where(
                Reservation.start_date < filters.end_date,
                Reservation.end_date > filters.start_date,
            )
        reservations = self.session.scalars(statement).all()
        if filters.customer is None:
            return reservations
        # SQLite NOCASE only handles ASCII. As in the public catalogue, casefold gives
        # Unicode-insensitive literal matching; '%' and '_' never become wildcards.
        query = filters.customer.casefold()
        return [
            item
            for item in reservations
            if query in item.customer_name.casefold() or query in item.customer_email.casefold()
        ]

    def conflicting_ids(self, equipment_id: int, start_date: date, end_date: date) -> list[int]:
        return list(
            self.session.scalars(
                select(Reservation.id)
                .where(
                    Reservation.equipment_id == equipment_id,
                    Reservation.status == "confirmed",
                    Reservation.start_date < end_date,
                    Reservation.end_date > start_date,
                )
                .order_by(Reservation.id)
            )
        )

    def active_counts_by_equipment(
        self, equipment_ids: Sequence[int], today: date
    ) -> dict[int, int]:
        if not equipment_ids:
            return {}
        # Aggregate in one query without loading private reservation/customer records.
        # Rentals use [start, end): a return today is already outside the rental period.
        return dict(
            self.session.execute(
                select(Reservation.equipment_id, func.count(Reservation.id))
                .where(
                    Reservation.equipment_id.in_(equipment_ids),
                    Reservation.status == "confirmed",
                    Reservation.end_date > today,
                )
                .group_by(Reservation.equipment_id)
            ).all()
        )

    def occupied_ranges(
        self, equipment_id: int, start_date: date, end_date: date
    ) -> list[tuple[date, date]]:
        # Select dates only: the calendar never needs customer data or reservation identifiers.
        return [
            (row.start_date, row.end_date)
            for row in self.session.execute(
                select(Reservation.start_date, Reservation.end_date)
                .where(
                    Reservation.equipment_id == equipment_id,
                    Reservation.status == "confirmed",
                    Reservation.start_date < end_date,
                    Reservation.end_date > start_date,
                )
                .order_by(Reservation.start_date, Reservation.end_date)
            )
        ]

    def active_date_ranges(
        self, equipment_ids: Sequence[int], today: date
    ) -> list[tuple[date, date]]:
        if not equipment_ids:
            return []
        # Keep one range per reservation, including coincident bookings on distinct units.
        # Only dates are selected: public callers never load private reservation records.
        return [
            (row.start_date, row.end_date)
            for row in self.session.execute(
                select(Reservation.start_date, Reservation.end_date)
                .where(
                    Reservation.equipment_id.in_(equipment_ids),
                    Reservation.status == "confirmed",
                    Reservation.end_date > today,
                )
                .order_by(Reservation.start_date, Reservation.end_date, Reservation.id)
            )
        ]

    def reference_exists(self, external_reference: str) -> bool:
        return (
            self.session.scalar(
                select(Reservation.id)
                .where(Reservation.external_reference == external_reference)
                .limit(1)
            )
            is not None
        )

    def add(self, reservation: Reservation) -> None:
        self.session.add(reservation)
