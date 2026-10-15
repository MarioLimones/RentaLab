from typing import Annotated

from fastapi import APIRouter, Body, Path, Query
from pydantic import ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from rentalab.autenticacion.dependencias import ClienteUsuario
from rentalab.base_datos import SQLITE_ENTERO_MAXIMO, inmediata_transaccion
from rentalab.compatibilidad import ModeloApi, entrada_http
from rentalab.cuenta.modelos import GuardadosProducto
from rentalab.equipo.grupos import activo_producto_unidades, producto_clave
from rentalab.equipo.modelos import Equipo
from rentalab.equipo.servicio import EquipoNoEncontrado
from rentalab.respuestas_http import RespuestaError, SesionBaseDatos

enrutador = APIRouter(prefix="/api/me/saved-products", tags=["Mis productos guardados"])
PositivoId = Annotated[int, Path(gt=0, le=SQLITE_ENTERO_MAXIMO)]
ERROR_RESPUESTAS = {
    401: {"model": RespuestaError, "description": "Sesión ausente, caducada o desactivada"},
    403: {"model": RespuestaError, "description": "Requiere rol cliente y CSRF en escrituras"},
    404: {"model": RespuestaError, "description": "El producto que se intenta guardar no existe"},
    503: {"model": RespuestaError, "description": "SQLite ocupada; reintento explícito posterior"},
}


class GuardadosProductosLectura(ModeloApi):
    model_config = ConfigDict(extra="forbid")

    ids_equipos: list[int]


class VacioParametros(ModeloApi):
    model_config = ConfigDict(extra="forbid")


def guardados_filas(
    sesion: Session, id_usuario_cliente: int
) -> list[tuple[GuardadosProducto, Equipo]]:
    return list(
        sesion.execute(
            select(GuardadosProducto, Equipo)
            .join(Equipo, GuardadosProducto.id_equipo == Equipo.id)
            .where(GuardadosProducto.id_usuario_cliente == id_usuario_cliente)
            .order_by(GuardadosProducto.id_equipo)
        ).tuples()
    )


def guardados_producto_ids(sesion: Session, id_usuario_cliente: int) -> GuardadosProductosLectura:
    # El representante público del modelo puede cambiar al archivarse una unidad.
    # Conserva el vínculo guardado y devuelve el identificador actual mientras esté disponible.
    # Los modelos completamente archivados conservan un identificador para poder eliminarlos.
    representantes: dict[tuple[str, str], int] = {}
    for elemento in sesion.scalars(
        select(Equipo).where(Equipo.activo.is_(True)).order_by(Equipo.id)
    ):
        representantes.setdefault(producto_clave(elemento), elemento.id)
    productos: dict[tuple[str, str], int] = {}
    for _guardados, equipo in guardados_filas(sesion, id_usuario_cliente):
        clave = producto_clave(equipo)
        productos.setdefault(clave, representantes.get(clave, equipo.id))
    return GuardadosProductosLectura(ids_equipos=sorted(productos.values()))


@enrutador.get(
    "",
    response_model=GuardadosProductosLectura,
    responses=ERROR_RESPUESTAS,
    summary="Listar los productos guardados de mi cuenta",
    description=(
        "Devuelve identificadores de modelos del catálogo, sin datos internos del inventario. "
        "Conserva los identificadores de productos retirados para poder quitarlos de la lista."
    ),
)
def listar_guardados_productos(
    identidad: ClienteUsuario,
    sesion: SesionBaseDatos,
    parametros: Annotated[VacioParametros, Query(), entrada_http(VacioParametros)],
) -> GuardadosProductosLectura:
    assert identidad.id_usuario is not None
    return guardados_producto_ids(sesion, identidad.id_usuario)


@enrutador.put(
    "/{equipment_id}",
    response_model=GuardadosProductosLectura,
    responses=ERROR_RESPUESTAS,
    summary="Guardar un producto activo una sola vez",
    description="Las unidades físicas del mismo modelo comparten un único producto guardado.",
)
def guardar_producto(
    id_equipo: Annotated[int, Path(alias="equipment_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    identidad: ClienteUsuario,
    sesion: SesionBaseDatos,
    parametros: Annotated[VacioParametros, Query(), entrada_http(VacioParametros)],
    datos: Annotated[VacioParametros | None, Body(), entrada_http(VacioParametros)] = None,
) -> GuardadosProductosLectura:
    assert identidad.id_usuario is not None
    with inmediata_transaccion(sesion):
        equipo = sesion.get(Equipo, id_equipo)
        if equipo is None or not equipo.activo:
            raise EquipoNoEncontrado
        canonico = activo_producto_unidades(sesion, equipo)[0]
        clave = producto_clave(canonico)
        if not any(
            producto_clave(elemento) == clave
            for _guardados, elemento in guardados_filas(sesion, identidad.id_usuario)
        ):
            sesion.add(
                GuardadosProducto(id_usuario_cliente=identidad.id_usuario, id_equipo=canonico.id)
            )
            sesion.flush()
        resultado = guardados_producto_ids(sesion, identidad.id_usuario)
    return resultado


@enrutador.delete(
    "/{equipment_id}",
    response_model=GuardadosProductosLectura,
    responses=ERROR_RESPUESTAS,
    summary="Quitar un producto guardado, incluso si se ha retirado del catálogo",
    description="Operación idempotente; también admite identificadores de unidades del modelo.",
)
def eliminar_guardados_producto(
    id_equipo: Annotated[int, Path(alias="equipment_id", gt=0, le=SQLITE_ENTERO_MAXIMO)],
    identidad: ClienteUsuario,
    sesion: SesionBaseDatos,
    parametros: Annotated[VacioParametros, Query(), entrada_http(VacioParametros)],
    datos: Annotated[VacioParametros | None, Body(), entrada_http(VacioParametros)] = None,
) -> GuardadosProductosLectura:
    assert identidad.id_usuario is not None
    with inmediata_transaccion(sesion):
        equipo = sesion.get(Equipo, id_equipo)
        if equipo is not None:
            clave = producto_clave(equipo)
            for guardados, elemento in guardados_filas(sesion, identidad.id_usuario):
                if producto_clave(elemento) == clave:
                    sesion.delete(guardados)
            sesion.flush()
        resultado = guardados_producto_ids(sesion, identidad.id_usuario)
    return resultado
