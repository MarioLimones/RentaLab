"""Calendario de negocio independiente de la zona del servidor e inyectable en pruebas HTTP."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends

HoyProveedor = Callable[[], date]


def utc_ahora() -> datetime:
    return datetime.now(UTC)


def madrid_hoy() -> date:
    return utc_ahora().astimezone(ZoneInfo("Europe/Madrid")).date()


def obtener_hoy_proveedor() -> HoyProveedor:
    # Devuelve un proveedor de fecha para consultarlo después de obtener el bloqueo.
    return madrid_hoy


NegocioFecha = Annotated[HoyProveedor, Depends(obtener_hoy_proveedor)]
