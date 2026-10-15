from collections.abc import Sequence
from typing import Annotated, Self
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Path, Query, Response
from pydantic import ConfigDict, Field, model_validator

from rentalab.autenticacion.dependencias import ClienteUsuario
from rentalab.base_datos import SQLITE_ENTERO_MAXIMO
from rentalab.compatibilidad import ModeloApi, entrada_http
from rentalab.reloj import NegocioFecha
from rentalab.reservas.esquemas import CrearReserva, IntervaloFechas, ReservaEstado
from rentalab.reservas.modelos import Reserva
from rentalab.reservas.repositorio import RepositorioReservas
from rentalab.reservas.servicio import ServicioReservas
from rentalab.respuestas_http import RespuestaError, SesionBaseDatos

enrutador = APIRouter(prefix="/api/me/reservations", tags=["Mis reservas"])
PositivoId = Annotated[int, Path(gt=0, le=SQLITE_ENTERO_MAXIMO)]
ERROR_RESPUESTAS = {
    401: {"model": RespuestaError, "description": "Sesión ausente, caducada o desactivada"},
    403: {"model": RespuestaError, "description": "Requiere rol cliente y CSRF en escrituras"},
    404: {"model": RespuestaError, "description": "Equipo o reserva propia inexistente"},
    409: {
        "model": RespuestaError,
        "description": "Fechas fuera de plazo o disponibilidad cambiada",
    },
    503: {"model": RespuestaError, "description": "SQLite ocupada; reintento explícito posterior"},
}


class ClienteReservaCrear(IntervaloFechas):
    id_equipo: Annotated[int, Field(strict=True, gt=0, le=SQLITE_ENTERO_MAXIMO)]


class ClienteReservaConjuntoCrear(IntervaloFechas):
    ids_equipos: Annotated[
        list[Annotated[int, Field(strict=True, gt=0, le=SQLITE_ENTERO_MAXIMO)]],
        Field(min_length=1, max_length=50),
    ]

    @model_validator(mode="after")
    def exigir_distintos_equipo(instancia) -> Self:
        if len(instancia.ids_equipos) != len(set(instancia.ids_equipos)):
            raise ValueError("Incluye cada producto una sola vez en la reserva conjunta")
        return instancia


class ClienteReservaLectura(IntervaloFechas):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    id_equipo: int
    estado: ReservaEstado


class VacioParametros(ModeloApi):
    model_config = ConfigDict(extra="forbid")


def obtener_servicio(sesion: SesionBaseDatos) -> ServicioReservas:
    return ServicioReservas(RepositorioReservas(sesion))


Servicio = Annotated[ServicioReservas, Depends(obtener_servicio)]


@enrutador.post(
    "",
    response_model=ClienteReservaLectura,
    status_code=201,
    responses=ERROR_RESPUESTAS,
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
def crear_reserva(
    datos: Annotated[ClienteReservaCrear, entrada_http(ClienteReservaCrear)],
    respuesta: Response,
    identidad: ClienteUsuario,
    servicio: Servicio,
    hoy: NegocioFecha,
    clave_idempotencia: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> Reserva:
    assert (
        identidad.id_usuario is not None
        and identidad.nombre is not None
        and identidad.correo is not None
    )
    reserva = servicio.crear_para_cliente(
        CrearReserva(
            **datos.model_dump(), nombre_cliente=identidad.nombre, correo_cliente=identidad.correo
        ),
        id_usuario_cliente=identidad.id_usuario,
        hoy=hoy,
        asignar_producto_unidad=True,
        clave_idempotencia=str(clave_idempotencia) if clave_idempotencia is not None else None,
    )
    respuesta.headers["Location"] = f"/api/me/reservations/{reserva.id}"
    return reserva


@enrutador.post(
    "/batch",
    response_model=list[ClienteReservaLectura],
    status_code=201,
    responses=ERROR_RESPUESTAS,
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
def crear_reserva_conjunto(
    datos: Annotated[ClienteReservaConjuntoCrear, entrada_http(ClienteReservaConjuntoCrear)],
    respuesta: Response,
    identidad: ClienteUsuario,
    servicio: Servicio,
    hoy: NegocioFecha,
    clave_idempotencia: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> list[Reserva]:
    assert (
        identidad.id_usuario is not None
        and identidad.nombre is not None
        and identidad.correo is not None
    )
    reservas = servicio.crear_conjunto_para_cliente(
        [
            CrearReserva(
                id_equipo=id_equipo,
                fecha_inicio=datos.fecha_inicio,
                fecha_fin=datos.fecha_fin,
                nombre_cliente=identidad.nombre,
                correo_cliente=identidad.correo,
            )
            for id_equipo in datos.ids_equipos
        ],
        id_usuario_cliente=identidad.id_usuario,
        hoy=hoy,
        clave_idempotencia=str(clave_idempotencia) if clave_idempotencia is not None else None,
    )
    respuesta.headers["Location"] = "/api/me/reservations"
    return reservas


@enrutador.get(
    "",
    response_model=list[ClienteReservaLectura],
    responses=ERROR_RESPUESTAS,
    summary="Listar exclusivamente mis reservas, incluido el historial cancelado",
)
def listar_reservas(
    identidad: ClienteUsuario,
    servicio: Servicio,
    parametros: Annotated[VacioParametros, Query(), entrada_http(VacioParametros)],
) -> Sequence[Reserva]:
    assert identidad.id_usuario is not None
    return servicio.listar_para_cliente(identidad.id_usuario)


@enrutador.get(
    "/{reservation_id}",
    response_model=ClienteReservaLectura,
    responses=ERROR_RESPUESTAS,
    summary="Consultar una reserva propia; las ajenas devuelven 404",
)
def obtener_reserva(
    id_reserva: Annotated[int, Path(alias="reservation_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    identidad: ClienteUsuario,
    servicio: Servicio,
) -> Reserva:
    assert identidad.id_usuario is not None
    return servicio.obtener_para_cliente(id_reserva, identidad.id_usuario)


@enrutador.post(
    "/{reservation_id}/cancel",
    response_model=ClienteReservaLectura,
    responses=ERROR_RESPUESTAS,
    summary="Cancelar antes del inicio en Europe/Madrid, conservando historial",
    description="Una reserva ya cancelada devuelve el mismo resultado, incluso pasado su inicio.",
)
def cancelar_reserva(
    id_reserva: Annotated[int, Path(alias="reservation_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    identidad: ClienteUsuario,
    servicio: Servicio,
    hoy: NegocioFecha,
    datos: Annotated[VacioParametros | None, Body(), entrada_http(VacioParametros)] = None,
) -> Reserva:
    assert identidad.id_usuario is not None
    return servicio.cancelar_para_cliente(
        id_reserva, id_usuario_cliente=identidad.id_usuario, hoy=hoy
    )
