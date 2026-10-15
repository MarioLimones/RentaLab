"""
Avisos del cliente: entradas y salidas explícitas sobre la escritura compartida de incidencias.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from pydantic import ConfigDict, StringConstraints

from rentalab.autenticacion.dependencias import ClienteUsuario
from rentalab.base_datos import SQLITE_ENTERO_MAXIMO
from rentalab.compatibilidad import ModeloApi, entrada_http
from rentalab.incidencias.esquemas import IncidenciaEstado, IncidenciaTitulo
from rentalab.incidencias.modelos import Incidencia
from rentalab.incidencias.repositorio import RepositorioIncidencias
from rentalab.incidencias.servicio import ConflictoIncidencia, IncidenciaNoEncontrada
from rentalab.reservas.servicio import ReservaNoEncontrada
from rentalab.respuestas_http import RespuestaError, SesionBaseDatos

enrutador = APIRouter(prefix="/api/me", tags=["Avisos del cliente"])
PositivoId = Annotated[int, Path(gt=0, le=SQLITE_ENTERO_MAXIMO)]
ClienteDescripcion = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=2000, pattern=r"^[^\x00]*$"
    ),
]


class ClienteIncidenciaCrear(ModeloApi):
    model_config = ConfigDict(extra="forbid")

    titulo: IncidenciaTitulo
    descripcion: ClienteDescripcion


class ClienteIncidenciaLectura(ModeloApi):
    # No heredes el esquema administrativo: cada campo publicado es deliberado.
    model_config = ConfigDict(extra="forbid")

    id: int
    id_reserva: int
    titulo: str
    descripcion: str
    estado: IncidenciaEstado
    respuesta_publica: str


class ClienteIncidenciaFiltros(ModeloApi):
    model_config = ConfigDict(extra="forbid")


class ClienteIncidenciaServicio:
    def __init__(instancia, repositorio: RepositorioIncidencias) -> None:
        instancia.repositorio = repositorio

    def crear(
        instancia, id_reserva: int, datos: ClienteIncidenciaCrear, *, id_usuario: int
    ) -> ClienteIncidenciaLectura:
        # La consulta de propiedad/estado y la inserción comparten el bloqueo de cancelación.
        with instancia.repositorio.escritura_transaccion():
            reserva = instancia.repositorio.obtener_propia_reserva(id_reserva, id_usuario)
            if reserva is None:
                raise ReservaNoEncontrada
            if reserva.estado != "confirmed":
                raise ConflictoIncidencia(
                    "Sólo puedes informar de problemas en una reserva confirmada"
                )
            incidencia = Incidencia(
                id_reserva=reserva.id,
                id_equipo=reserva.id_equipo,
                id_usuario_autor=id_usuario,
                titulo=datos.titulo,
                descripcion=datos.descripcion,
                prioridad="medium",
                bloqueante=False,
                estado="open",
                resolucion="",
                respuesta_publica="",
                notas_internas="",
            )
            instancia.repositorio.agregar(incidencia)
            instancia.repositorio.sincronizar()
            resultado = instancia._lectura(incidencia)
        return resultado

    def listar(instancia, *, id_usuario: int) -> list[ClienteIncidenciaLectura]:
        return [
            instancia._lectura(incidencia)
            for incidencia in instancia.repositorio.listar_cliente_incidencias(id_usuario)
        ]

    def obtener(instancia, id_incidencia: int, *, id_usuario: int) -> ClienteIncidenciaLectura:
        incidencia = instancia.repositorio.obtener_cliente_incidencia(id_incidencia, id_usuario)
        if incidencia is None:
            raise IncidenciaNoEncontrada
        return instancia._lectura(incidencia)

    @staticmethod
    def _lectura(incidencia: Incidencia) -> ClienteIncidenciaLectura:
        assert incidencia.id_reserva is not None
        return ClienteIncidenciaLectura(
            id=incidencia.id,
            id_reserva=incidencia.id_reserva,
            titulo=incidencia.titulo,
            descripcion=incidencia.descripcion,
            estado=incidencia.estado,
            respuesta_publica=incidencia.respuesta_publica,
        )


def obtener_servicio(sesion: SesionBaseDatos) -> ClienteIncidenciaServicio:
    return ClienteIncidenciaServicio(RepositorioIncidencias(sesion))


Servicio = Annotated[ClienteIncidenciaServicio, Depends(obtener_servicio)]
ERROR_RESPUESTAS = {
    404: {
        "model": RespuestaError,
        "description": "Reserva o aviso no encontrado entre los propios",
    },
    409: {
        "model": RespuestaError,
        "description": "La reserva no está confirmada o SQLite está ocupada; reintenta",
    },
}


@enrutador.post(
    "/reservations/{reservation_id}/incidents",
    response_model=ClienteIncidenciaLectura,
    status_code=201,
    responses=ERROR_RESPUESTAS,
    summary="Informar de un problema en una reserva propia confirmada",
    description=(
        "El servidor deduce autor y equipo. Registra un aviso abierto no bloqueante, "
        "pendiente de gestión administrativa. Sólo acepta título y descripción."
    ),
)
def crear_cliente_incidencia(
    id_reserva: Annotated[int, Path(alias="reservation_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    datos: Annotated[ClienteIncidenciaCrear, entrada_http(ClienteIncidenciaCrear)],
    respuesta: Response,
    servicio: Servicio,
    identidad: ClienteUsuario,
) -> ClienteIncidenciaLectura:
    assert identidad.id_usuario is not None
    resultado = servicio.crear(id_reserva, datos, id_usuario=identidad.id_usuario)
    respuesta.headers["Location"] = f"/api/me/incidents/{resultado.id}"
    return resultado


@enrutador.get(
    "/incidents",
    response_model=list[ClienteIncidenciaLectura],
    summary="Consultar los avisos propios y su respuesta pública",
)
def listar_cliente_incidencias(
    servicio: Servicio,
    identidad: ClienteUsuario,
    filtros: Annotated[ClienteIncidenciaFiltros, Query(), entrada_http(ClienteIncidenciaFiltros)],
) -> list[ClienteIncidenciaLectura]:
    assert identidad.id_usuario is not None
    return servicio.listar(id_usuario=identidad.id_usuario)


@enrutador.get(
    "/incidents/{incident_id}",
    response_model=ClienteIncidenciaLectura,
    responses=ERROR_RESPUESTAS,
    summary="Consultar un aviso propio sin información interna de gestión",
)
def obtener_cliente_incidencia(
    id_incidencia: Annotated[int, Path(alias="incident_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    servicio: Servicio,
    identidad: ClienteUsuario,
) -> ClienteIncidenciaLectura:
    assert identidad.id_usuario is not None
    return servicio.obtener(id_incidencia, id_usuario=identidad.id_usuario)
