"""Customer reports: explicit input/output boundaries over the shared incident writer."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from pydantic import BaseModel, ConfigDict, StringConstraints

from rentalab.auth.dependencies import CustomerUser
from rentalab.database import SQLITE_MAX_INTEGER
from rentalab.http import DatabaseSession, ErrorResponse
from rentalab.incidents.models import Incident
from rentalab.incidents.repository import IncidentRepository
from rentalab.incidents.schemas import IncidentStatus, IncidentTitle
from rentalab.incidents.service import IncidentConflict, IncidentNotFound
from rentalab.reservations.service import ReservationNotFound

router = APIRouter(prefix="/api/me", tags=["Avisos del cliente"])
PositiveId = Annotated[int, Path(gt=0, le=SQLITE_MAX_INTEGER)]
CustomerDescription = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=2000, pattern=r"^[^\x00]*$"
    ),
]


class CustomerIncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: IncidentTitle
    description: CustomerDescription


class CustomerIncidentRead(BaseModel):
    # Do not inherit the administrative schema: each published field is intentional.
    model_config = ConfigDict(extra="forbid")

    id: int
    reservation_id: int
    title: str
    description: str
    status: IncidentStatus
    public_response: str


class CustomerIncidentFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerIncidentService:
    def __init__(self, repository: IncidentRepository) -> None:
        self.repository = repository

    def create(
        self, reservation_id: int, data: CustomerIncidentCreate, *, user_id: int
    ) -> CustomerIncidentRead:
        # The ownership/status read and insert run under the same writer lock as cancel.
        with self.repository.write_transaction():
            reservation = self.repository.get_owned_reservation(reservation_id, user_id)
            if reservation is None:
                raise ReservationNotFound
            if reservation.status != "confirmed":
                raise IncidentConflict(
                    "Sólo puedes informar de problemas en una reserva confirmada"
                )
            incident = Incident(
                reservation_id=reservation.id,
                equipment_id=reservation.equipment_id,
                author_user_id=user_id,
                title=data.title,
                description=data.description,
                priority="medium",
                blocking=False,
                status="open",
                resolution="",
                public_response="",
                internal_notes="",
            )
            self.repository.add(incident)
            self.repository.flush()
            result = self._read(incident)
        return result

    def list(self, *, user_id: int) -> list[CustomerIncidentRead]:
        return [
            self._read(incident) for incident in self.repository.list_customer_incidents(user_id)
        ]

    def get(self, incident_id: int, *, user_id: int) -> CustomerIncidentRead:
        incident = self.repository.get_customer_incident(incident_id, user_id)
        if incident is None:
            raise IncidentNotFound
        return self._read(incident)

    @staticmethod
    def _read(incident: Incident) -> CustomerIncidentRead:
        assert incident.reservation_id is not None
        return CustomerIncidentRead(
            id=incident.id,
            reservation_id=incident.reservation_id,
            title=incident.title,
            description=incident.description,
            status=incident.status,
            public_response=incident.public_response,
        )


def get_service(session: DatabaseSession) -> CustomerIncidentService:
    return CustomerIncidentService(IncidentRepository(session))


Service = Annotated[CustomerIncidentService, Depends(get_service)]
ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Reserva o aviso no encontrado entre los propios"},
    409: {
        "model": ErrorResponse,
        "description": "La reserva no está confirmada o SQLite está ocupada; reintenta",
    },
}


@router.post(
    "/reservations/{reservation_id}/incidents",
    response_model=CustomerIncidentRead,
    status_code=201,
    responses=ERROR_RESPONSES,
    summary="Informar de un problema en una reserva propia confirmada",
    description=(
        "El servidor deduce autor y equipo. Registra un aviso abierto no bloqueante, "
        "pendiente de gestión administrativa. Sólo acepta título y descripción."
    ),
)
def create_customer_incident(
    reservation_id: PositiveId,
    data: CustomerIncidentCreate,
    response: Response,
    service: Service,
    identity: CustomerUser,
) -> CustomerIncidentRead:
    assert identity.user_id is not None
    result = service.create(reservation_id, data, user_id=identity.user_id)
    response.headers["Location"] = f"/api/me/incidents/{result.id}"
    return result


@router.get(
    "/incidents",
    response_model=list[CustomerIncidentRead],
    summary="Consultar los avisos propios y su respuesta pública",
)
def list_customer_incidents(
    service: Service,
    identity: CustomerUser,
    filters: Annotated[CustomerIncidentFilters, Query()],
) -> list[CustomerIncidentRead]:
    assert identity.user_id is not None
    return service.list(user_id=identity.user_id)


@router.get(
    "/incidents/{incident_id}",
    response_model=CustomerIncidentRead,
    responses=ERROR_RESPONSES,
    summary="Consultar un aviso propio sin información interna de gestión",
)
def get_customer_incident(
    incident_id: PositiveId, service: Service, identity: CustomerUser
) -> CustomerIncidentRead:
    assert identity.user_id is not None
    return service.get(incident_id, user_id=identity.user_id)
