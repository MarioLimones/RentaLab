from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from rentalab.autenticacion.dependencias import AdministradorUsuario, exigir_administrador
from rentalab.base_datos import SQLITE_ENTERO_MAXIMO
from rentalab.compatibilidad import entrada_http
from rentalab.incidencias.esquemas import (
    IncidenciaActualizar,
    IncidenciaCrear,
    IncidenciaEstadoCambiar,
    IncidenciaFiltros,
    IncidenciaLectura,
)
from rentalab.incidencias.repositorio import RepositorioIncidencias
from rentalab.incidencias.servicio import ServicioIncidencias
from rentalab.respuestas_http import RespuestaError, SesionBaseDatos

enrutador = APIRouter(prefix="/api/incidents", tags=["Incidencias"])
PositivoId = Annotated[int, Path(gt=0, le=SQLITE_ENTERO_MAXIMO)]
ERROR_RESPUESTAS = {
    404: {"model": RespuestaError, "description": "Equipo o incidencia inexistente"},
    409: {
        "model": RespuestaError,
        "description": "Transición de negocio inválida",
    },
    503: {
        "model": RespuestaError,
        "description": "SQLite temporalmente ocupada; reintentar después de Retry-After",
        "headers": {
            "Retry-After": {
                "schema": {"type": "integer"},
                "description": "Segundos antes de reintentar un bloqueo",
            }
        },
    },
}


def obtener_servicio(sesion: SesionBaseDatos) -> ServicioIncidencias:
    return ServicioIncidencias(RepositorioIncidencias(sesion))


Servicio = Annotated[ServicioIncidencias, Depends(obtener_servicio)]


@enrutador.post(
    "",
    response_model=IncidenciaLectura,
    status_code=201,
    responses=ERROR_RESPUESTAS,
    summary="Registrar una incidencia y avisar de reservas confirmadas",
)
def crear_incidencia(
    datos: Annotated[IncidenciaCrear, entrada_http(IncidenciaCrear)],
    respuesta: Response,
    servicio: Servicio,
    identidad: AdministradorUsuario,
) -> IncidenciaLectura:
    incidencia = servicio.crear(datos, id_usuario_autor=identidad.id_usuario)
    respuesta.headers["Location"] = f"/api/incidents/{incidencia.id}"
    return incidencia


@enrutador.get(
    "",
    dependencies=[Depends(exigir_administrador)],
    response_model=list[IncidenciaLectura],
    responses=ERROR_RESPUESTAS,
    summary="Listar incidencias, incluidas las resueltas",
)
def listar_incidencias(
    servicio: Servicio,
    filtros: Annotated[IncidenciaFiltros, Query(), entrada_http(IncidenciaFiltros)],
) -> list[IncidenciaLectura]:
    return servicio.listar(filtros)


@enrutador.get(
    "/{incident_id}",
    response_model=IncidenciaLectura,
    responses=ERROR_RESPUESTAS,
    summary="Consultar una incidencia y sus reservas confirmadas actuales",
)
def obtener_incidencia(
    id_incidencia: Annotated[int, Path(alias="incident_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    servicio: Servicio,
    identidad: AdministradorUsuario,
) -> IncidenciaLectura:
    return servicio.obtener(id_incidencia)


@enrutador.patch(
    "/{incident_id}",
    dependencies=[Depends(exigir_administrador)],
    response_model=IncidenciaLectura,
    responses=ERROR_RESPUESTAS,
    summary="Gestionar prioridad, bloqueo, respuesta al cliente y notas internas",
    description=(
        "Sólo administración decide el bloqueo y la prioridad. public_response es visible "
        "al cliente autor; internal_notes y resolution son exclusivamente internos. "
        "Omitir conserva el valor; texto vacío borra una comunicación, null se rechaza."
    ),
)
def actualizar_incidencia(
    id_incidencia: Annotated[int, Path(alias="incident_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    datos: Annotated[IncidenciaActualizar, entrada_http(IncidenciaActualizar)],
    servicio: Servicio,
) -> IncidenciaLectura:
    return servicio.actualizar(id_incidencia, datos)


@enrutador.patch(
    "/{incident_id}/status",
    dependencies=[Depends(exigir_administrador)],
    response_model=IncidenciaLectura,
    responses=ERROR_RESPUESTAS,
    summary="Cambiar de estado; resolver exige una explicación no vacía",
    description="Sólo open → in_progress, open → resolved e in_progress → resolved.",
)
def cambiar_incidencia_estado(
    id_incidencia: Annotated[int, Path(alias="incident_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    datos: Annotated[IncidenciaEstadoCambiar, entrada_http(IncidenciaEstadoCambiar)],
    servicio: Servicio,
) -> IncidenciaLectura:
    return servicio.cambiar_estado(id_incidencia, datos)
