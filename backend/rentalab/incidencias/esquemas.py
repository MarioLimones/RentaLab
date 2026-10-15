from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, StrictBool, StringConstraints, model_validator
from pydantic.json_schema import SkipJsonSchema

from rentalab.base_datos import SQLITE_ENTERO_MAXIMO
from rentalab.compatibilidad import ModeloApi

IncidenciaPrioridad = Literal["low", "medium", "high"]
IncidenciaEstado = Literal["open", "in_progress", "resolved"]
IncidenciaTitulo = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=160, pattern=r"^[^\x00]*$"
    ),
]
IncidenciaTexto = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, max_length=2000, pattern=r"^[^\x00]*$"),
]


class IncidenciaCrear(ModeloApi):
    model_config = ConfigDict(extra="forbid")

    id_equipo: Annotated[int, Field(strict=True, gt=0, le=SQLITE_ENTERO_MAXIMO)]
    titulo: IncidenciaTitulo
    descripcion: IncidenciaTexto = ""
    prioridad: IncidenciaPrioridad = "medium"
    bloqueante: StrictBool = False


class IncidenciaEstadoCambiar(ModeloApi):
    model_config = ConfigDict(extra="forbid")

    estado: IncidenciaEstado
    resolucion: IncidenciaTexto | None = Field(
        default=None,
        description="Explicación no vacía al resolver; omitir o null en otros estados",
    )

    @model_validator(mode="after")
    def exigir_resolucion_solo_cuando_resolviendo(instancia) -> Self:
        if instancia.estado == "resolved" and not instancia.resolucion:
            raise ValueError("Resolver exige una explicación no vacía")
        if instancia.estado != "resolved" and instancia.resolucion is not None:
            raise ValueError("La explicación de resolución sólo se admite al resolver")
        return instancia


class IncidenciaFiltros(ModeloApi):
    model_config = ConfigDict(extra="forbid")

    id_equipo: Annotated[int, Field(gt=0, le=SQLITE_ENTERO_MAXIMO)] | None = None
    estado: IncidenciaEstado | None = None
    prioridad: IncidenciaPrioridad | None = None
    bloqueante: bool | None = None


class IncidenciaActualizar(ModeloApi):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})

    prioridad: IncidenciaPrioridad | SkipJsonSchema[None] = None
    bloqueante: StrictBool | SkipJsonSchema[None] = None
    respuesta_publica: IncidenciaTexto | SkipJsonSchema[None] = None
    notas_internas: IncidenciaTexto | SkipJsonSchema[None] = None

    @model_validator(mode="after")
    def exigir_no_nulo_cambios(instancia) -> Self:
        if not instancia.model_fields_set:
            raise ValueError("Indica al menos un campo para editar")
        if any(getattr(instancia, campo) is None for campo in instancia.model_fields_set):
            raise ValueError("Los campos enviados no pueden ser nulos")
        return instancia


class IncidenciaLectura(IncidenciaCrear):
    id: int
    id_reserva: int | None = None
    id_usuario_autor: int | None = None
    estado: IncidenciaEstado
    resolucion: IncidenciaTexto
    respuesta_publica: IncidenciaTexto = ""
    notas_internas: IncidenciaTexto = ""
    ids_reservas_confirmadas: list[int] = Field(
        description="Reservas actualmente confirmadas del equipo; sin filtrar por fecha"
    )
    aviso: str | None = Field(description="Aviso calculado; las reservas existentes se conservan")
