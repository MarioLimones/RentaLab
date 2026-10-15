from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date

from sqlalchemy.exc import IntegrityError

from rentalab.availability import AvailabilityService
from rentalab.equipment.groups import active_product_units, product_key
from rentalab.equipment.service import EquipmentNotFound
from rentalab.reservations.models import (
    BookingRequestReservation,
    CustomerBookingRequest,
    Reservation,
)
from rentalab.reservations.repository import ReservationRepository
from rentalab.reservations.schemas import (
    AvailabilityRead,
    DateRange,
    ReservationByCode,
    ReservationCreate,
    ReservationFilters,
    ReservationOrigin,
    ReservationStatus,
)


class ReservationNotFound(Exception):
    pass


class ReservationConflict(Exception):
    pass


@dataclass(frozen=True)
class ReservationImportResult:
    reservation: Reservation
    created: bool


class ReservationService:
    def __init__(self, repository: ReservationRepository) -> None:
        self.repository = repository
        self.availability_service = AvailabilityService(repository)

    def get(self, reservation_id: int) -> Reservation:
        reservation = self.repository.get(reservation_id)
        if reservation is None:
            raise ReservationNotFound
        return reservation

    def list(self, filters: ReservationFilters) -> Sequence[Reservation]:
        if (
            filters.equipment_id is not None
            and self.repository.get_equipment(filters.equipment_id) is None
        ):
            raise EquipmentNotFound
        return self.repository.list(filters)

    def availability(self, equipment_id: int, date_range: DateRange) -> AvailabilityRead:
        return self.availability_service.check(equipment_id, date_range)

    def create(self, data: ReservationCreate) -> Reservation:
        with self._write_transaction():
            reservation = self._create_checked(data)
        return reservation

    def create_for_customer(
        self,
        data: ReservationCreate,
        *,
        customer_user_id: int,
        today: Callable[[], date],
        initial_status: ReservationStatus = "confirmed",
        allocate_product_unit: bool = False,
        idempotency_key: str | None = None,
    ) -> Reservation:
        # The customer's policy and shared availability reads run under the same write lock.
        with self._write_transaction():
            requested = data
            replay = self._replay_customer_request(
                [requested], customer_user_id, idempotency_key, operation="single"
            )
            if replay is not None:
                return replay[0]
            if data.start_date < today():
                raise ReservationConflict("La fecha de inicio no puede ser anterior a hoy")
            try:
                # Portal customers choose a product; the reservation still belongs to one
                # physical unit for the entire interval. Explicit demo bookings retain
                # their requested unit unless allocation is deliberately enabled.
                if allocate_product_unit:
                    data = self._allocate_product_unit(data)
                reservation = self._create_checked(
                    data, customer_user_id=customer_user_id, origin="portal"
                )
                # The explicit local demo may insert its cancelled example in this same
                # transaction. HTTP inputs never accept or supply an initial status.
                reservation.status = initial_status
                self._record_customer_request(
                    [requested],
                    [reservation],
                    customer_user_id,
                    idempotency_key,
                    operation="single",
                )
            except ReservationConflict as error:
                # The client can learn availability, never the reason for an internal block.
                raise ReservationConflict(
                    "El equipo no está disponible para esas fechas; "
                    "consulta la disponibilidad y elige otro intervalo"
                ) from error
        return reservation

    def _allocate_product_unit(self, data: ReservationCreate) -> ReservationCreate:
        equipment = self.repository.get_equipment(data.equipment_id)
        if equipment is None:
            raise EquipmentNotFound
        if not equipment.active:
            raise ReservationConflict("El equipo está inactivo")
        date_range = DateRange(start_date=data.start_date, end_date=data.end_date)
        for unit in active_product_units(self.repository.session, equipment):
            if self.availability(unit.id, date_range).available:
                return data.model_copy(update={"equipment_id": unit.id})
        raise ReservationConflict("No hay ninguna unidad disponible para todo el intervalo")

    def create_batch_for_customer(
        self,
        data: Sequence[ReservationCreate],
        *,
        customer_user_id: int,
        today: Callable[[], date],
        idempotency_key: str | None = None,
    ) -> list[Reservation]:
        # All products share the lock used by single, admin and import reservations.
        # A later failure rolls back every earlier allocation and insertion.
        with self._write_transaction():
            replay = self._replay_customer_request(
                data, customer_user_id, idempotency_key, operation="batch"
            )
            if replay is not None:
                return replay
            business_day = today()
            if any(item.start_date < business_day for item in data):
                raise ReservationConflict("La fecha de inicio no puede ser anterior a hoy")
            products: set[tuple[str, str]] = set()
            for item in data:
                equipment = self.repository.get_equipment(item.equipment_id)
                if equipment is None:
                    raise EquipmentNotFound
                key = product_key(equipment)
                if key in products:
                    raise ReservationConflict(
                        "Incluye cada producto una sola vez en la reserva conjunta"
                    )
                products.add(key)
            try:
                reservations = [
                    self._create_checked(
                        self._allocate_product_unit(item),
                        customer_user_id=customer_user_id,
                        origin="portal",
                    )
                    for item in data
                ]
                self._record_customer_request(
                    data, reservations, customer_user_id, idempotency_key, operation="batch"
                )
            except ReservationConflict as error:
                raise ReservationConflict(
                    "Uno de los productos no está disponible para esas fechas; "
                    "no se ha creado ninguna reserva. "
                    "Consulta la disponibilidad y elige otro intervalo"
                ) from error
        return reservations

    def _replay_customer_request(
        self,
        data: Sequence[ReservationCreate],
        customer_user_id: int,
        idempotency_key: str | None,
        *,
        operation: str,
    ) -> list[Reservation] | None:
        if idempotency_key is None:
            return None
        previous = self.repository.get_booking_request(customer_user_id, idempotency_key)
        if previous is None:
            return None
        if (
            previous.operation != operation
            or [item.requested_equipment_id for item in previous.items]
            != [item.equipment_id for item in data]
            or previous.start_date != data[0].start_date
            or previous.end_date != data[0].end_date
        ):
            raise ReservationConflict(
                "Esta solicitud de reserva ya se utilizó con otros datos; "
                "inicia una nueva solicitud para cambiar equipo o fechas"
            )
        # Replay precedes current date/activity/availability, even after cancellation.
        reservations = self.repository.reservations_for_booking_request(
            customer_user_id, idempotency_key
        )
        if len(reservations) != len(data):
            raise ReservationNotFound
        return reservations

    def _record_customer_request(
        self,
        data: Sequence[ReservationCreate],
        reservations: Sequence[Reservation],
        customer_user_id: int,
        idempotency_key: str | None,
        *,
        operation: str,
    ) -> None:
        if idempotency_key is None:
            return
        self.repository.add_booking_request(
            CustomerBookingRequest(
                customer_user_id=customer_user_id,
                idempotency_key=idempotency_key,
                operation=operation,
                start_date=data[0].start_date,
                end_date=data[0].end_date,
                items=[
                    BookingRequestReservation(
                        position=position,
                        requested_equipment_id=requested.equipment_id,
                        reservation=reservation,
                    )
                    for position, (requested, reservation) in enumerate(
                        zip(data, reservations, strict=True)
                    )
                ],
            )
        )

    def create_from_code(self, data: ReservationByCode) -> ReservationImportResult:
        with self._write_transaction():
            existing = self.repository.get_by_reference(data.external_reference)
            equipment = self.repository.get_equipment_by_code(data.equipment_code)
            if existing is not None:
                identical = equipment is not None and (
                    existing.equipment_id == equipment.id
                    and existing.customer_name == data.customer_name
                    and existing.customer_email == data.customer_email
                    and existing.start_date == data.start_date
                    and existing.end_date == data.end_date
                )
                if not identical:
                    raise ReservationConflict(
                        "La referencia externa ya existe con datos distintos; "
                        "no se modifica la reserva."
                    )
                outcome = ReservationImportResult(existing, created=False)
            else:
                if equipment is None:
                    raise EquipmentNotFound
                reservation = self._create_checked(
                    ReservationCreate(
                        equipment_id=equipment.id,
                        **data.model_dump(exclude={"equipment_code"}),
                    ),
                    origin="csv",
                )
                outcome = ReservationImportResult(reservation, created=True)
        return outcome

    def _create_checked(
        self,
        data: ReservationCreate,
        *,
        customer_user_id: int | None = None,
        origin: ReservationOrigin = "admin",
    ) -> Reservation:
        availability = self.availability(
            data.equipment_id,
            DateRange(
                start_date=data.start_date,
                end_date=data.end_date,
            ),
        )
        if not availability.available:
            if availability.reason == "equipment_inactive":
                raise ReservationConflict("El equipo está inactivo")
            if availability.reason == "blocking_incident":
                raise ReservationConflict("El equipo tiene una incidencia bloqueante sin resolver")
            raise ReservationConflict("El equipo ya tiene una reserva confirmada en ese intervalo")
        if data.external_reference is not None and self.repository.reference_exists(
            data.external_reference
        ):
            raise ReservationConflict("La referencia externa ya está asociada a una reserva")
        reservation = Reservation(
            **data.model_dump(),
            status="confirmed",
            customer_user_id=customer_user_id,
            origin=origin,
        )
        self.repository.add(reservation)
        return reservation

    @contextmanager
    def _write_transaction(self) -> Iterator[None]:
        try:
            with self.repository.write_transaction():
                yield
        except IntegrityError as error:
            if getattr(error.orig, "sqlite_errorcode", None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE:
                raise ReservationConflict(
                    "La referencia externa ya está asociada a una reserva"
                ) from error
            raise

    def cancel(self, reservation_id: int) -> Reservation:
        with self.repository.write_transaction():
            reservation = self.get(reservation_id)
            reservation.status = "cancelled"
        return reservation

    def get_for_customer(self, reservation_id: int, customer_user_id: int) -> Reservation:
        reservation = self.repository.get_for_customer(reservation_id, customer_user_id)
        if reservation is None:
            raise ReservationNotFound
        return reservation

    def list_for_customer(self, customer_user_id: int) -> Sequence[Reservation]:
        return self.repository.list_for_customer(customer_user_id)

    def cancel_for_customer(
        self, reservation_id: int, *, customer_user_id: int, today: Callable[[], date]
    ) -> Reservation:
        with self.repository.write_transaction():
            reservation = self.get_for_customer(reservation_id, customer_user_id)
            # Repeated cancellation remains a successful read, including after its start day.
            if reservation.status == "cancelled":
                return reservation
            if today() >= reservation.start_date:
                raise ReservationConflict(
                    "Solo puedes cancelar una reserva antes de su fecha de inicio"
                )
            reservation.status = "cancelled"
        return reservation
