"""Identidad pública del producto conservando registros físicos de inventario independientes."""

from unicodedata import normalize

from sqlalchemy import select
from sqlalchemy.orm import Session

from rentalab.equipo.modelos import Equipo


def producto_clave(equipo: Equipo) -> tuple[str, str]:
    # Los nombres describen modelos y los códigos identifican unidades físicas en administración.
    return tuple(
        normalize("NFC", valor.strip()).casefold() for valor in (equipo.nombre, equipo.categoria)
    )


def activo_producto_unidades(sesion: Session, equipo: Equipo) -> list[Equipo]:
    clave = producto_clave(equipo)
    return [
        elemento
        for elemento in sesion.scalars(
            select(Equipo).where(Equipo.activo.is_(True)).order_by(Equipo.id)
        )
        if producto_clave(elemento) == clave
    ]
