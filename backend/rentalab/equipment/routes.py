from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response

from rentalab.auth.dependencies import require_admin
from rentalab.database import SQLITE_MAX_INTEGER
from rentalab.equipment.models import Equipment
from rentalab.equipment.repository import EquipmentRepository
from rentalab.equipment.schemas import EquipmentCreate, EquipmentRead, EquipmentUpdate
from rentalab.equipment.service import EquipmentService
from rentalab.http import DatabaseSession, ErrorResponse

router = APIRouter(prefix="/api/equipment", tags=["Equipos"], dependencies=[Depends(require_admin)])
EquipmentId = Annotated[int, Path(gt=0, le=SQLITE_MAX_INTEGER)]
ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Equipo inexistente"},
    409: {"model": ErrorResponse, "description": "Código ya utilizado por otra unidad"},
}


def get_service(session: DatabaseSession) -> EquipmentService:
    return EquipmentService(EquipmentRepository(session))


Service = Annotated[EquipmentService, Depends(get_service)]


@router.get("", response_model=list[EquipmentRead], summary="Listar equipos")
def list_equipment(service: Service, active: bool | None = None) -> Sequence[Equipment]:
    return service.list(active)


@router.post(
    "",
    response_model=EquipmentRead,
    status_code=201,
    responses={409: ERROR_RESPONSES[409]},
    summary="Crear una unidad física",
)
def create_equipment(data: EquipmentCreate, response: Response, service: Service) -> Equipment:
    equipment = service.create(data)
    response.headers["Location"] = f"/api/equipment/{equipment.id}"
    return equipment


@router.get(
    "/{equipment_id}",
    response_model=EquipmentRead,
    responses={404: ERROR_RESPONSES[404]},
    summary="Consultar un equipo",
)
def get_equipment(equipment_id: EquipmentId, service: Service) -> Equipment:
    return service.get(equipment_id)


@router.put(
    "/{equipment_id}",
    response_model=EquipmentRead,
    responses=ERROR_RESPONSES,
    summary="Reemplazar los datos de un equipo",
)
def replace_equipment(
    equipment_id: EquipmentId, data: EquipmentCreate, service: Service
) -> Equipment:
    return service.update(equipment_id, data)


@router.patch(
    "/{equipment_id}",
    response_model=EquipmentRead,
    responses=ERROR_RESPONSES,
    summary="Editar campos o activar/desactivar un equipo",
)
def update_equipment(
    equipment_id: EquipmentId, data: EquipmentUpdate, service: Service
) -> Equipment:
    return service.update(equipment_id, data)
