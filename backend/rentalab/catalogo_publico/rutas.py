from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import FileResponse

from rentalab.base_datos import SQLITE_ENTERO_MAXIMO
from rentalab.catalogo_publico.esquemas import (
    PublicoCalendarioConsulta,
    PublicoCalendarioLectura,
    PublicoCatalogoFiltros,
    PublicoDisponibilidadLectura,
    PublicoEquipoLectura,
    PublicoFechaIntervalo,
    PublicoReservasConsulta,
    PublicoReservasLectura,
)
from rentalab.catalogo_publico.medio import PUBLICO_RECURSOS, RECURSOS_DIRECTORIO
from rentalab.catalogo_publico.servicio import ServicioCatalogoPublico
from rentalab.compatibilidad import entrada_http
from rentalab.reloj import NegocioFecha
from rentalab.respuestas_http import RespuestaError, SesionBaseDatos

enrutador = APIRouter(prefix="/api/public", tags=["Catálogo público"])
EquipoId = Annotated[int, Path(gt=0, le=SQLITE_ENTERO_MAXIMO)]
NO_ENCONTRADO = {404: {"model": RespuestaError, "description": "Equipo inexistente o inactivo"}}


def obtener_servicio(sesion: SesionBaseDatos, hoy: NegocioFecha) -> ServicioCatalogoPublico:
    return ServicioCatalogoPublico(sesion, hoy)


Servicio = Annotated[ServicioCatalogoPublico, Depends(obtener_servicio)]


@enrutador.get(
    "/equipment",
    response_model=list[PublicoEquipoLectura],
    summary="Listar equipos activos del catálogo público",
    description=(
        "Una ficha por modelo (nombre y categoría), ordenada por nombre e identificador. "
        "La búsqueda q es un fragmento literal del nombre y category coincide exactamente; "
        "ambas ignoran mayúsculas/minúsculas y espacios exteriores. "
        "Sin fechas no se afirma disponibilidad."
    ),
)
def listar_equipo(
    servicio: Servicio,
    filtros: Annotated[PublicoCatalogoFiltros, Query(), entrada_http(PublicoCatalogoFiltros)],
) -> list[PublicoEquipoLectura]:
    return servicio.listar(filtros)


@enrutador.get(
    "/equipment/{equipment_id}",
    response_model=PublicoEquipoLectura,
    responses=NO_ENCONTRADO,
    summary="Consultar características públicas de un equipo activo",
)
def obtener_equipo(
    id_equipo: Annotated[int, Path(alias="equipment_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    servicio: Servicio,
) -> PublicoEquipoLectura:
    return servicio.obtener(id_equipo)


@enrutador.get(
    "/equipment/{equipment_id}/reservations",
    response_model=PublicoReservasLectura,
    responses=NO_ENCONTRADO,
    summary="Consultar fechas de las reservas actuales y futuras de un modelo",
    description=(
        "Una entrada por reserva confirmada de las unidades activas del modelo, sin datos "
        "de clientes ni identificadores de reservas o unidades. Inicio incluido y fin excluido; "
        "sólo se incluyen reservas con fin posterior a hoy en Europe/Madrid. "
        "Conserva fechas originales y reservas coincidentes; no admite filtros."
    ),
)
def equipo_reservas(
    id_equipo: Annotated[int, Path(alias="equipment_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    servicio: Servicio,
    parametros: Annotated[PublicoReservasConsulta, Query(), entrada_http(PublicoReservasConsulta)],
) -> PublicoReservasLectura:
    return servicio.reserva_fechas(id_equipo)


@enrutador.get(
    "/equipment/{equipment_id}/availability",
    response_model=PublicoDisponibilidadLectura,
    responses=NO_ENCONTRADO,
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
def equipo_disponibilidad(
    id_equipo: Annotated[int, Path(alias="equipment_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    fechas: Annotated[PublicoFechaIntervalo, Query(), entrada_http(PublicoFechaIntervalo)],
    servicio: Servicio,
) -> PublicoDisponibilidadLectura:
    return servicio.comprobar_disponibilidad(id_equipo, fechas)


@enrutador.get(
    "/equipment/{equipment_id}/calendar",
    response_model=PublicoCalendarioLectura,
    responses=NO_ENCONTRADO,
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
def equipo_calendario(
    id_equipo: Annotated[int, Path(alias="equipment_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    fechas: Annotated[PublicoCalendarioConsulta, Query(), entrada_http(PublicoCalendarioConsulta)],
    servicio: Servicio,
) -> PublicoCalendarioLectura:
    return servicio.calendario(id_equipo, fechas)


@enrutador.get("/images/{filename}", include_in_schema=False)
def catalogo_imagen(nombre_archivo: Annotated[str, Path(alias="filename")]) -> FileResponse:
    medio_tipo = PUBLICO_RECURSOS.get(nombre_archivo)
    if medio_tipo is None:
        raise HTTPException(status_code=404, detail="Recurso inexistente")
    return FileResponse(RECURSOS_DIRECTORIO / nombre_archivo, media_type=medio_tipo)
