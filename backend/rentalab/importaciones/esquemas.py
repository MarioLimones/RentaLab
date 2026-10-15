from typing import Literal

from pydantic import Field

from rentalab.compatibilidad import ModeloApi
from rentalab.reservas.esquemas import LecturaReserva

ImportacionFilaEstado = Literal["accepted", "already_imported", "rejected"]


class ImportacionFilaResultado(ModeloApi):
    linea: int = Field(ge=2, description="Línea física inicial del registro; cabecera en línea 1")
    referencia_externa: str | None
    estado: ImportacionFilaEstado
    reserva: LecturaReserva | None
    mensaje: str


class ImportacionTotales(ModeloApi):
    total: int = Field(ge=0)
    aceptadas: int = Field(default=0, ge=0)
    ya_importadas: int = Field(default=0, ge=0)
    rechazadas: int = Field(default=0, ge=0)


class ImportacionInforme(ModeloApi):
    totales: ImportacionTotales
    filas: list[ImportacionFilaResultado]
