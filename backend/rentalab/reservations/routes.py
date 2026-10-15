from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from rentalab.auth.dependencies import require_admin
from rentalab.database import SQLITE_MAX_INTEGER
from rentalab.http import DatabaseSession, ErrorResponse
from rentalab.reservations.models import Reservation
from rentalab.reservations.repository import ReservationRepository
from rentalab.reservations.schemas import (
    AvailabilityRead,
    DateRange,
    ReservationCreate,
    ReservationFilters,
    ReservationRead,
)
from rentalab.reservations.service import ReservationService

router = APIRouter(prefix="/api/reservations", tags=["Reservas"])
availability_router = APIRouter(
    prefix="/api/equipment", tags=["Disponibilidad"], dependencies=[Depends(require_admin)]
)
PositiveId = Annotated[int, Path(gt=0, le=SQLITE_MAX_INTEGER)]
ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Equipo o reserva inexistente"},
    409: {
        "model": ErrorResponse,
        "description": "Conflicto de negocio: fechas o referencia no disponibles",
    },
    503: {
        "model": ErrorResponse,
        "description": "SQLite temporalmente ocupada; no implica falta de disponibilidad",
        "headers": {
            "Retry-After": {
                "schema": {"type": "integer"},
                "description": "Segundos antes de reintentar si SQLite está ocupada",
            }
        },
    },
}


def get_service(session: DatabaseSession) -> ReservationService:
    return ReservationService(ReservationRepository(session))


Service = Annotated[ReservationService, Depends(get_service)]


@router.post(
    "",
    dependencies=[Depends(require_admin)],
    response_model=ReservationRead,
    status_code=201,
    responses=ERROR_RESPONSES,
    summary="Confirmar una reserva de días completos",
)
def create_reservation(
    data: ReservationCreate, response: Response, service: Service
) -> Reservation:
    reservation = service.create(data)
    response.headers["Location"] = f"/api/reservations/{reservation.id}"
    return reservation


@router.get(
    "",
    dependencies=[Depends(require_admin)],
    response_model=list[ReservationRead],
    responses=ERROR_RESPONSES,
    summary="Listar todas las reservas por cliente, equipo, fechas, estado y origen",
)
def list_reservations(
    service: Service, filters: Annotated[ReservationFilters, Query()]
) -> Sequence[Reservation]:
    return service.list(filters)


@router.get(
    "/{reservation_id}",
    dependencies=[Depends(require_admin)],
    response_model=ReservationRead,
    responses=ERROR_RESPONSES,
    summary="Consultar una reserva y su estado actual",
)
def get_reservation(reservation_id: PositiveId, service: Service) -> Reservation:
    return service.get(reservation_id)


@router.post(
    "/{reservation_id}/cancel",
    dependencies=[Depends(require_admin)],
    response_model=ReservationRead,
    responses=ERROR_RESPONSES,
    summary="Cancelar sin borrar el historial; operación idempotente",
)
def cancel_reservation(reservation_id: PositiveId, service: Service) -> Reservation:
    return service.cancel(reservation_id)


@availability_router.get(
    "/{equipment_id}/availability",
    response_model=AvailabilityRead,
    responses=ERROR_RESPONSES,
    summary="Consultar disponibilidad para [inicio, fin)",
    description=(
        "Consulta informativa; crear una reserva vuelve a evaluar las reglas de forma atómica."
    ),
)
def equipment_availability(
    equipment_id: PositiveId,
    date_range: Annotated[DateRange, Query()],
    service: Service,
) -> AvailabilityRead:
    return service.availability(equipment_id, date_range)
