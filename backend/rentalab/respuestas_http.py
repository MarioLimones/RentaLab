from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from rentalab.compatibilidad import ModeloApi


class RespuestaError(ModeloApi):
    detalle: str


def obtener_sesion(solicitud: Request) -> Iterator[Session]:
    with solicitud.app.state.fabrica_sesiones() as sesion:
        yield sesion


SesionBaseDatos = Annotated[Session, Depends(obtener_sesion)]
