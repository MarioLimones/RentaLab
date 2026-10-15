from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from rentalab.autenticacion.dependencias import exigir_administrador
from rentalab.base_datos import SQLITE_ENTERO_MAXIMO
from rentalab.compatibilidad import entrada_http
from rentalab.equipo.esquemas import ActualizarEquipo, CrearEquipo, LecturaEquipo
from rentalab.equipo.modelos import Equipo
from rentalab.equipo.repositorio import RepositorioEquipos
from rentalab.equipo.servicio import ServicioEquipos
from rentalab.respuestas_http import RespuestaError, SesionBaseDatos

enrutador = APIRouter(
    prefix="/api/equipment", tags=["Equipos"], dependencies=[Depends(exigir_administrador)]
)
EquipoId = Annotated[int, Path(gt=0, le=SQLITE_ENTERO_MAXIMO)]
ERROR_RESPUESTAS = {
    404: {"model": RespuestaError, "description": "Equipo inexistente"},
    409: {"model": RespuestaError, "description": "Código ya utilizado por otra unidad"},
}


def obtener_servicio(sesion: SesionBaseDatos) -> ServicioEquipos:
    return ServicioEquipos(RepositorioEquipos(sesion))


Servicio = Annotated[ServicioEquipos, Depends(obtener_servicio)]


@enrutador.get("", response_model=list[LecturaEquipo], summary="Listar equipos")
def listar_equipo(
    servicio: Servicio, activo: Annotated[bool | None, Query(alias="active")] = None
) -> Sequence[Equipo]:
    return servicio.listar(activo)


@enrutador.post(
    "",
    response_model=LecturaEquipo,
    status_code=201,
    responses={409: ERROR_RESPUESTAS[409]},
    summary="Crear una unidad física",
)
def crear_equipo(
    datos: Annotated[CrearEquipo, entrada_http(CrearEquipo)],
    respuesta: Response,
    servicio: Servicio,
) -> Equipo:
    equipo = servicio.crear(datos)
    respuesta.headers["Location"] = f"/api/equipment/{equipo.id}"
    return equipo


@enrutador.get(
    "/{equipment_id}",
    response_model=LecturaEquipo,
    responses={404: ERROR_RESPUESTAS[404]},
    summary="Consultar un equipo",
)
def obtener_equipo(
    id_equipo: Annotated[int, Path(alias="equipment_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    servicio: Servicio,
) -> Equipo:
    return servicio.obtener(id_equipo)


@enrutador.put(
    "/{equipment_id}",
    response_model=LecturaEquipo,
    responses=ERROR_RESPUESTAS,
    summary="Reemplazar los datos de un equipo",
)
def reemplazar_equipo(
    id_equipo: Annotated[int, Path(alias="equipment_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    datos: Annotated[CrearEquipo, entrada_http(CrearEquipo)],
    servicio: Servicio,
) -> Equipo:
    return servicio.actualizar(id_equipo, datos)


@enrutador.patch(
    "/{equipment_id}",
    response_model=LecturaEquipo,
    responses=ERROR_RESPUESTAS,
    summary="Editar campos o activar/desactivar un equipo",
)
def actualizar_equipo(
    id_equipo: Annotated[int, Path(alias="equipment_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    datos: Annotated[ActualizarEquipo, entrada_http(ActualizarEquipo)],
    servicio: Servicio,
) -> Equipo:
    return servicio.actualizar(id_equipo, datos)
