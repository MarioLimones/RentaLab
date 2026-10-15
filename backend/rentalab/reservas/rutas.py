from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from rentalab.autenticacion.dependencias import exigir_administrador
from rentalab.base_datos import SQLITE_ENTERO_MAXIMO
from rentalab.compatibilidad import entrada_http
from rentalab.reservas.esquemas import (
    CrearReserva,
    DisponibilidadLectura,
    FiltrosReservas,
    IntervaloFechas,
    LecturaReserva,
)
from rentalab.reservas.modelos import Reserva
from rentalab.reservas.repositorio import RepositorioReservas
from rentalab.reservas.servicio import ServicioReservas
from rentalab.respuestas_http import RespuestaError, SesionBaseDatos

enrutador = APIRouter(prefix="/api/reservations", tags=["Reservas"])
disponibilidad_enrutador = APIRouter(
    prefix="/api/equipment", tags=["Disponibilidad"], dependencies=[Depends(exigir_administrador)]
)
PositivoId = Annotated[int, Path(gt=0, le=SQLITE_ENTERO_MAXIMO)]
ERROR_RESPUESTAS = {
    404: {"model": RespuestaError, "description": "Equipo o reserva inexistente"},
    409: {
        "model": RespuestaError,
        "description": "Conflicto de negocio: fechas o referencia no disponibles",
    },
    503: {
        "model": RespuestaError,
        "description": "SQLite temporalmente ocupada; no implica falta de disponibilidad",
        "headers": {
            "Retry-After": {
                "schema": {"type": "integer"},
                "description": "Segundos antes de reintentar si SQLite está ocupada",
            }
        },
    },
}


def obtener_servicio(sesion: SesionBaseDatos) -> ServicioReservas:
    return ServicioReservas(RepositorioReservas(sesion))


Servicio = Annotated[ServicioReservas, Depends(obtener_servicio)]


@enrutador.post(
    "",
    dependencies=[Depends(exigir_administrador)],
    response_model=LecturaReserva,
    status_code=201,
    responses=ERROR_RESPUESTAS,
    summary="Confirmar una reserva de días completos",
)
def crear_reserva(
    datos: Annotated[CrearReserva, entrada_http(CrearReserva)],
    respuesta: Response,
    servicio: Servicio,
) -> Reserva:
    reserva = servicio.crear(datos)
    respuesta.headers["Location"] = f"/api/reservations/{reserva.id}"
    return reserva


@enrutador.get(
    "",
    dependencies=[Depends(exigir_administrador)],
    response_model=list[LecturaReserva],
    responses=ERROR_RESPUESTAS,
    summary="Listar todas las reservas por cliente, equipo, fechas, estado y origen",
)
def listar_reservas(
    servicio: Servicio, filtros: Annotated[FiltrosReservas, Query(), entrada_http(FiltrosReservas)]
) -> Sequence[Reserva]:
    return servicio.listar(filtros)


@enrutador.get(
    "/{reservation_id}",
    dependencies=[Depends(exigir_administrador)],
    response_model=LecturaReserva,
    responses=ERROR_RESPUESTAS,
    summary="Consultar una reserva y su estado actual",
)
def obtener_reserva(
    id_reserva: Annotated[int, Path(alias="reservation_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    servicio: Servicio,
) -> Reserva:
    return servicio.obtener(id_reserva)


@enrutador.post(
    "/{reservation_id}/cancel",
    dependencies=[Depends(exigir_administrador)],
    response_model=LecturaReserva,
    responses=ERROR_RESPUESTAS,
    summary="Cancelar sin borrar el historial; operación idempotente",
)
def cancelar_reserva(
    id_reserva: Annotated[int, Path(alias="reservation_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    servicio: Servicio,
) -> Reserva:
    return servicio.cancelar(id_reserva)


@disponibilidad_enrutador.get(
    "/{equipment_id}/availability",
    response_model=DisponibilidadLectura,
    responses=ERROR_RESPUESTAS,
    summary="Consultar disponibilidad para [inicio, fin)",
    description=(
        "Consulta informativa; crear una reserva vuelve a evaluar las reglas de forma atómica."
    ),
)
def equipo_disponibilidad(
    id_equipo: Annotated[int, Path(alias="equipment_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    fecha_intervalo: Annotated[IntervaloFechas, Query(), entrada_http(IntervaloFechas)],
    servicio: Servicio,
) -> DisponibilidadLectura:
    return servicio.disponibilidad(id_equipo, fecha_intervalo)
