import re
from datetime import date
from typing import Annotated, Literal, Self

from email_validator import EmailNotValidError, validate_email
from pydantic import (
    AfterValidator,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from rentalab.base_datos import SQLITE_ENTERO_MAXIMO
from rentalab.compatibilidad import ModeloApi
from rentalab.equipo.esquemas import EquipoCodigo


def exigir_iso_fecha(valor: object) -> object:
    if type(valor) is date:
        return valor
    if not isinstance(valor, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", valor) is None:
        raise ValueError("Usa una fecha ISO con formato YYYY-MM-DD")
    return valor


def normalizar_cliente_correo(valor: str) -> str:
    try:
        return validate_email(valor, check_deliverability=False, test_environment=True).normalized
    except EmailNotValidError as error:
        raise ValueError("El correo del cliente no es válido") from error


IsoFecha = Annotated[date, BeforeValidator(exigir_iso_fecha)]
ReservaEstado = Literal["confirmed", "cancelled"]
ReservaOrigen = Literal["portal", "admin", "csv", "legacy"]
ExternaReferencia = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=120, pattern=r"^[^\x00]*$"
    ),
]
ClienteNombre = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=120, pattern=r"^[^\x00]*$"
    ),
]
ClienteCorreo = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=254),
    AfterValidator(normalizar_cliente_correo),
    Field(json_schema_extra={"format": "email"}),
]


class IntervaloFechas(ModeloApi):
    model_config = ConfigDict(extra="forbid")

    fecha_inicio: IsoFecha = Field(description="Inicio incluido, YYYY-MM-DD")
    fecha_fin: IsoFecha = Field(description="Fin excluido, estrictamente posterior al inicio")

    @model_validator(mode="after")
    def exigir_positivo_intervalo(instancia) -> Self:
        if instancia.fecha_fin <= instancia.fecha_inicio:
            raise ValueError("La fecha de fin debe ser posterior a la de inicio")
        return instancia


class CrearReserva(IntervaloFechas):
    id_equipo: Annotated[int, Field(strict=True, gt=0, le=SQLITE_ENTERO_MAXIMO)]
    nombre_cliente: ClienteNombre
    correo_cliente: ClienteCorreo
    referencia_externa: ExternaReferencia | None = None


class LecturaReserva(CrearReserva):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    estado: ReservaEstado
    id_usuario_cliente: int | None
    origen: ReservaOrigen


class ReservaPorCodigo(IntervaloFechas):
    codigo_equipo: EquipoCodigo
    nombre_cliente: ClienteNombre
    correo_cliente: ClienteCorreo
    referencia_externa: ExternaReferencia


class FiltrosReservas(ModeloApi):
    model_config = ConfigDict(extra="forbid")

    id_equipo: Annotated[int, Field(gt=0, le=SQLITE_ENTERO_MAXIMO)] | None = None
    estado: ReservaEstado | None = None
    cliente: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True, min_length=1, max_length=254, pattern=r"^[^\x00]*$"
            ),
        ]
        | None
    ) = Field(
        default=None, description="Subcadena literal de nombre o correo, sin distinguir mayúsculas"
    )
    id_usuario_cliente: Annotated[int, Field(gt=0, le=SQLITE_ENTERO_MAXIMO)] | None = None
    origen: ReservaOrigen | None = None
    fecha_inicio: IsoFecha | None = None
    fecha_fin: IsoFecha | None = None

    @model_validator(mode="after")
    def exigir_completo_intervalo(instancia) -> Self:
        if (instancia.fecha_inicio is None) != (instancia.fecha_fin is None):
            raise ValueError("Envía start_date y end_date juntos para filtrar por intervalo")
        if instancia.fecha_inicio is not None and instancia.fecha_fin is not None:
            IntervaloFechas(fecha_inicio=instancia.fecha_inicio, fecha_fin=instancia.fecha_fin)
        return instancia


class DisponibilidadLectura(IntervaloFechas):
    id_equipo: int
    disponible: bool
    motivo: Literal["equipment_inactive", "blocking_incident", "reservation_overlap"] | None
    ids_reservas_en_conflicto: list[int]
