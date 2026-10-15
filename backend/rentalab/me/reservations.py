from collections.abc import Sequence
from typing import Annotated, Self
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Path, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from rentalab.auth.dependencies import CustomerUser
from rentalab.clock import BusinessDate
from rentalab.database import SQLITE_MAX_INTEGER
from rentalab.http import DatabaseSession, ErrorResponse
from rentalab.reservations.models import Reservation
from rentalab.reservations.repository import ReservationRepository
from rentalab.reservations.schemas import DateRange, ReservationCreate, ReservationStatus
from rentalab.reservations.service import ReservationService

router = APIRouter(prefix="/api/me/reservations", tags=["Mis reservas"])
PositiveId = Annotated[int, Path(gt=0, le=SQLITE_MAX_INTEGER)]
ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Sesión ausente, caducada o desactivada"},
    403: {"model": ErrorResponse, "description": "Requiere rol cliente y CSRF en escrituras"},
    404: {"model": ErrorResponse, "description": "Equipo o reserva propia inexistente"},
    409: {
        "model": ErrorResponse,
        "description": "Fechas fuera de plazo o disponibilidad cambiada",
    },
    503: {"model": ErrorResponse, "description": "SQLite ocupada; reintento explícito posterior"},
}


class CustomerReservationCreate(DateRange):
    equipment_id: Annotated[int, Field(strict=True, gt=0, le=SQLITE_MAX_INTEGER)]


class CustomerReservationBatchCreate(DateRange):
    equipment_ids: Annotated[
        list[Annotated[int, Field(strict=True, gt=0, le=SQLITE_MAX_INTEGER)]],
        Field(min_length=1, max_length=50),
    ]

    @model_validator(mode="after")
    def require_distinct_equipment(self) -> Self:
        if len(self.equipment_ids) != len(set(self.equipment_ids)):
            raise ValueError("Incluye cada producto una sola vez en la reserva conjunta")
        return self


class CustomerReservationRead(DateRange):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    equipment_id: int
    status: ReservationStatus


class EmptyParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")


def get_service(session: DatabaseSession) -> ReservationService:
    return ReservationService(ReservationRepository(session))


Service = Annotated[ReservationService, Depends(get_service)]


@router.post(
    "",
    response_model=CustomerReservationRead,
    status_code=201,
    responses=ERROR_RESPONSES,
    summary="Confirmar una reserva propia para [inicio, fin)",
    description=(
        "Solo acepta equipo y fechas ISO. La identidad y el propietario proceden de la sesión. "
        "El equipo identifica un modelo; se asigna una unidad física libre para todo el periodo. "
        "Se comprueba disponibilidad dentro de la transacción; la consulta previa es orientativa. "
        "No admite un inicio anterior a hoy en Europe/Madrid."
        " Idempotency-Key opcional (UUID): repetir la misma solicitud devuelve su reserva "
        "original; reutilizar la clave con equipo o fechas distintos devuelve 409."
    ),
)
def create_reservation(
    data: CustomerReservationCreate,
    response: Response,
    identity: CustomerUser,
    service: Service,
    today: BusinessDate,
    idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> Reservation:
    assert identity.user_id is not None and identity.name is not None and identity.email is not None
    reservation = service.create_for_customer(
        ReservationCreate(
            **data.model_dump(), customer_name=identity.name, customer_email=identity.email
        ),
        customer_user_id=identity.user_id,
        today=today,
        allocate_product_unit=True,
        idempotency_key=str(idempotency_key) if idempotency_key is not None else None,
    )
    response.headers["Location"] = f"/api/me/reservations/{reservation.id}"
    return reservation


@router.post(
    "/batch",
    response_model=list[CustomerReservationRead],
    status_code=201,
    responses=ERROR_RESPONSES,
    summary="Confirmar varios productos juntos para el mismo intervalo [inicio, fin)",
    description=(
        "Acepta entre 1 y 50 productos distintos y fechas ISO comunes. "
        "La identidad y el propietario proceden de la sesión. "
        "Cada producto se asigna a una unidad física libre para todo el periodo. "
        "La disponibilidad se comprueba dentro de una única transacción: "
        "se confirman todos los productos o no se crea ninguna reserva. "
        "La consulta previa es orientativa. No admite un inicio anterior a hoy en Europe/Madrid."
        " Idempotency-Key opcional (UUID): repetir la misma solicitud conjunta devuelve "
        "sus reservas originales; cambiar la operación, productos o fechas con esa clave "
        "devuelve 409."
    ),
)
def create_reservation_batch(
    data: CustomerReservationBatchCreate,
    response: Response,
    identity: CustomerUser,
    service: Service,
    today: BusinessDate,
    idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> list[Reservation]:
    assert identity.user_id is not None and identity.name is not None and identity.email is not None
    reservations = service.create_batch_for_customer(
        [
            ReservationCreate(
                equipment_id=equipment_id,
                start_date=data.start_date,
                end_date=data.end_date,
                customer_name=identity.name,
                customer_email=identity.email,
            )
            for equipment_id in data.equipment_ids
        ],
        customer_user_id=identity.user_id,
        today=today,
        idempotency_key=str(idempotency_key) if idempotency_key is not None else None,
    )
    response.headers["Location"] = "/api/me/reservations"
    return reservations


@router.get(
    "",
    response_model=list[CustomerReservationRead],
    responses=ERROR_RESPONSES,
    summary="Listar exclusivamente mis reservas, incluido el historial cancelado",
)
def list_reservations(
    identity: CustomerUser,
    service: Service,
    parameters: Annotated[EmptyParameters, Query()],
) -> Sequence[Reservation]:
    assert identity.user_id is not None
    return service.list_for_customer(identity.user_id)


@router.get(
    "/{reservation_id}",
    response_model=CustomerReservationRead,
    responses=ERROR_RESPONSES,
    summary="Consultar una reserva propia; las ajenas devuelven 404",
)
def get_reservation(
    reservation_id: PositiveId, identity: CustomerUser, service: Service
) -> Reservation:
    assert identity.user_id is not None
    return service.get_for_customer(reservation_id, identity.user_id)


@router.post(
    "/{reservation_id}/cancel",
    response_model=CustomerReservationRead,
    responses=ERROR_RESPONSES,
    summary="Cancelar antes del inicio en Europe/Madrid, conservando historial",
    description="Una reserva ya cancelada devuelve el mismo resultado, incluso pasado su inicio.",
)
def cancel_reservation(
    reservation_id: PositiveId,
    identity: CustomerUser,
    service: Service,
    today: BusinessDate,
    data: Annotated[EmptyParameters | None, Body()] = None,
) -> Reservation:
    assert identity.user_id is not None
    return service.cancel_for_customer(
        reservation_id, customer_user_id=identity.user_id, today=today
    )
