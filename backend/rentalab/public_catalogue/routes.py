from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import FileResponse

from rentalab.clock import BusinessDate
from rentalab.database import SQLITE_MAX_INTEGER
from rentalab.http import DatabaseSession, ErrorResponse
from rentalab.public_catalogue.media import ASSETS_DIRECTORY, PUBLIC_ASSETS
from rentalab.public_catalogue.schemas import (
    PublicAvailabilityRead,
    PublicCalendarQuery,
    PublicCalendarRead,
    PublicCatalogueFilters,
    PublicDateRange,
    PublicEquipmentRead,
    PublicReservationsQuery,
    PublicReservationsRead,
)
from rentalab.public_catalogue.service import PublicCatalogueService

router = APIRouter(prefix="/api/public", tags=["Catálogo público"])
EquipmentId = Annotated[int, Path(gt=0, le=SQLITE_MAX_INTEGER)]
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Equipo inexistente o inactivo"}}


def get_service(session: DatabaseSession, today: BusinessDate) -> PublicCatalogueService:
    return PublicCatalogueService(session, today)


Service = Annotated[PublicCatalogueService, Depends(get_service)]


@router.get(
    "/equipment",
    response_model=list[PublicEquipmentRead],
    summary="Listar equipos activos del catálogo público",
    description=(
        "Una ficha por modelo (nombre y categoría), ordenada por nombre e identificador. "
        "La búsqueda q es un fragmento literal del nombre y category coincide exactamente; "
        "ambas ignoran mayúsculas/minúsculas y espacios exteriores. "
        "Sin fechas no se afirma disponibilidad."
    ),
)
def list_equipment(
    service: Service, filters: Annotated[PublicCatalogueFilters, Query()]
) -> list[PublicEquipmentRead]:
    return service.list(filters)


@router.get(
    "/equipment/{equipment_id}",
    response_model=PublicEquipmentRead,
    responses=NOT_FOUND,
    summary="Consultar características públicas de un equipo activo",
)
def get_equipment(equipment_id: EquipmentId, service: Service) -> PublicEquipmentRead:
    return service.get(equipment_id)


@router.get(
    "/equipment/{equipment_id}/reservations",
    response_model=PublicReservationsRead,
    responses=NOT_FOUND,
    summary="Consultar fechas de las reservas actuales y futuras de un modelo",
    description=(
        "Una entrada por reserva confirmada de las unidades activas del modelo, sin datos "
        "de clientes ni identificadores de reservas o unidades. Inicio incluido y fin excluido; "
        "sólo se incluyen reservas con fin posterior a hoy en Europe/Madrid. "
        "Conserva fechas originales y reservas coincidentes; no admite filtros."
    ),
)
def equipment_reservations(
    equipment_id: EquipmentId,
    service: Service,
    parameters: Annotated[PublicReservationsQuery, Query()],
) -> PublicReservationsRead:
    return service.reservation_dates(equipment_id)


@router.get(
    "/equipment/{equipment_id}/availability",
    response_model=PublicAvailabilityRead,
    responses=NOT_FOUND,
    summary="Consultar disponibilidad orientativa para [inicio, fin)",
    description=(
        "Alquiler por días completos, con inicio incluido y fin excluido. "
        "Envía start_date y end_date juntos para afirmar disponibilidad. "
        "Sin ambas fechas devuelve available=null y status=select_dates. "
        "Disponible si una unidad activa y sin incidencias bloqueantes está libre para "
        "todo el intervalo, sin publicar el motivo ni datos privados. "
        "Confirmar una reserva vuelve a comprobar las reglas dentro de la transacción."
    ),
)
def equipment_availability(
    equipment_id: EquipmentId,
    dates: Annotated[PublicDateRange, Query()],
    service: Service,
) -> PublicAvailabilityRead:
    return service.check_availability(equipment_id, dates)


@router.get(
    "/equipment/{equipment_id}/calendar",
    response_model=PublicCalendarRead,
    responses=NOT_FOUND,
    summary="Consultar días ocupados sin datos personales",
    description=(
        "Rango obligatorio [inicio, fin), de hasta 366 días. Publica únicamente intervalos "
        "en los que todas las unidades utilizables están ocupadas. Las canceladas no ocupan días. "
        "can_book=false indica que ninguna unidad admite reservas, sin detalles internos. "
        "Con booking_start, unavailable_end_dates impide devoluciones sin una única unidad "
        "libre para todo el alquiler; la ventana desde recogida admite hasta 366 días. "
        "Es orientativo: confirmar vuelve a comprobar las reglas dentro de la transacción."
    ),
)
def equipment_calendar(
    equipment_id: EquipmentId,
    dates: Annotated[PublicCalendarQuery, Query()],
    service: Service,
) -> PublicCalendarRead:
    return service.calendar(equipment_id, dates)


@router.get("/images/{filename}", include_in_schema=False)
def catalogue_image(filename: str) -> FileResponse:
    media_type = PUBLIC_ASSETS.get(filename)
    if media_type is None:
        raise HTTPException(status_code=404, detail="Recurso inexistente")
    return FileResponse(ASSETS_DIRECTORY / filename, media_type=media_type)
