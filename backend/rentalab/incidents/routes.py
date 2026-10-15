from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from rentalab.auth.dependencies import AdminUser, require_admin
from rentalab.database import SQLITE_MAX_INTEGER
from rentalab.http import DatabaseSession, ErrorResponse
from rentalab.incidents.repository import IncidentRepository
from rentalab.incidents.schemas import (
    IncidentCreate,
    IncidentFilters,
    IncidentRead,
    IncidentStatusChange,
    IncidentUpdate,
)
from rentalab.incidents.service import IncidentService

router = APIRouter(prefix="/api/incidents", tags=["Incidencias"])
PositiveId = Annotated[int, Path(gt=0, le=SQLITE_MAX_INTEGER)]
ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Equipo o incidencia inexistente"},
    409: {
        "model": ErrorResponse,
        "description": "Transición de negocio inválida",
    },
    503: {
        "model": ErrorResponse,
        "description": "SQLite temporalmente ocupada; reintentar después de Retry-After",
        "headers": {
            "Retry-After": {
                "schema": {"type": "integer"},
                "description": "Segundos antes de reintentar un bloqueo",
            }
        },
    },
}


def get_service(session: DatabaseSession) -> IncidentService:
    return IncidentService(IncidentRepository(session))


Service = Annotated[IncidentService, Depends(get_service)]


@router.post(
    "",
    response_model=IncidentRead,
    status_code=201,
    responses=ERROR_RESPONSES,
    summary="Registrar una incidencia y avisar de reservas confirmadas",
)
def create_incident(
    data: IncidentCreate, response: Response, service: Service, identity: AdminUser
) -> IncidentRead:
    incident = service.create(data, author_user_id=identity.user_id)
    response.headers["Location"] = f"/api/incidents/{incident.id}"
    return incident


@router.get(
    "",
    dependencies=[Depends(require_admin)],
    response_model=list[IncidentRead],
    responses=ERROR_RESPONSES,
    summary="Listar incidencias, incluidas las resueltas",
)
def list_incidents(
    service: Service, filters: Annotated[IncidentFilters, Query()]
) -> list[IncidentRead]:
    return service.list(filters)


@router.get(
    "/{incident_id}",
    response_model=IncidentRead,
    responses=ERROR_RESPONSES,
    summary="Consultar una incidencia y sus reservas confirmadas actuales",
)
def get_incident(incident_id: PositiveId, service: Service, identity: AdminUser) -> IncidentRead:
    return service.get(incident_id)


@router.patch(
    "/{incident_id}",
    dependencies=[Depends(require_admin)],
    response_model=IncidentRead,
    responses=ERROR_RESPONSES,
    summary="Gestionar prioridad, bloqueo, respuesta al cliente y notas internas",
    description=(
        "Sólo administración decide el bloqueo y la prioridad. public_response es visible "
        "al cliente autor; internal_notes y resolution son exclusivamente internos. "
        "Omitir conserva el valor; texto vacío borra una comunicación, null se rechaza."
    ),
)
def update_incident(
    incident_id: PositiveId, data: IncidentUpdate, service: Service
) -> IncidentRead:
    return service.update(incident_id, data)


@router.patch(
    "/{incident_id}/status",
    dependencies=[Depends(require_admin)],
    response_model=IncidentRead,
    responses=ERROR_RESPONSES,
    summary="Cambiar de estado; resolver exige una explicación no vacía",
    description="Sólo open → in_progress, open → resolved e in_progress → resolved.",
)
def change_incident_status(
    incident_id: PositiveId, data: IncidentStatusChange, service: Service
) -> IncidentRead:
    return service.change_status(incident_id, data)
