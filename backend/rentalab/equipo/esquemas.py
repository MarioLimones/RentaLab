import re
from typing import Annotated, Self
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema

from rentalab.compatibilidad import ModeloApi


def normalizar_codigo(valor: object) -> object:
    return valor.strip().upper() if isinstance(valor, str) else valor


def rechazar_nul(valor: str) -> str:
    if "\x00" in valor:
        raise ValueError("El texto no puede contener NUL")
    return valor


EquipoCodigo = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9_-]*$"),
    BeforeValidator(normalizar_codigo),
]
EquipoNombre = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=120),
    AfterValidator(rechazar_nul),
]
EquipoCategoria = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=80),
    AfterValidator(rechazar_nul),
]
EquipoDescripcion = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, max_length=2000),
    AfterValidator(rechazar_nul),
]


def rechazar_duplicado_caracteristica_nombres(valor: object) -> object:
    if isinstance(valor, dict):
        normalizado = [clave.strip() for clave in valor if isinstance(clave, str)]
        if len(normalizado) != len(set(normalizado)):
            raise ValueError("Las características no pueden repetir un nombre normalizado")
    return valor


def validar_imagen_url(valor: str) -> str:
    if "\\" in valor or any(ord(caracter) <= 32 or ord(caracter) == 127 for caracter in valor):
        raise ValueError("La imagen debe usar una URL HTTPS o una ruta de imagen pública local")
    try:
        analizada = urlsplit(valor)
        # Leer el puerto también valida números mal formados o fuera de rango.
        _ = analizada.port
    except ValueError as error:
        raise ValueError("La URL de la imagen no es válida") from error
    if analizada.query or analizada.fragment:
        raise ValueError("La URL de la imagen no admite consulta ni fragmento")
    if (
        analizada.scheme == "https"
        and analizada.hostname
        and analizada.username is None
        and analizada.password is None
    ):
        return valor
    local_prefijo = "/api/public/images/"
    if not analizada.scheme and not analizada.netloc and valor.startswith(local_prefijo):
        segmentos = valor.removeprefix(local_prefijo).split("/")
        if all(
            segmento not in {".", ".."} and re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", segmento)
            for segmento in segmentos
        ):
            return valor
    raise ValueError("La imagen debe usar una URL HTTPS o una ruta de imagen pública local")


EquipoPublicoDescripcion = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, max_length=2000),
    AfterValidator(rechazar_nul),
]
TecnicasCaracteristicaNombre = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=80),
    AfterValidator(rechazar_nul),
]
TecnicasCaracteristicaValor = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=300),
    AfterValidator(rechazar_nul),
]
EquipoTecnicasCaracteristicas = Annotated[
    dict[TecnicasCaracteristicaNombre, TecnicasCaracteristicaValor],
    Field(strict=True, max_length=20),
    BeforeValidator(rechazar_duplicado_caracteristica_nombres),
]
EquipoImagenUrl = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2048),
    AfterValidator(validar_imagen_url),
    Field(
        description="URL HTTPS sin credenciales, consulta ni fragmento, o /api/public/images/..."
    ),
]


class CrearEquipo(ModeloApi):
    model_config = ConfigDict(extra="forbid")

    codigo: EquipoCodigo
    nombre: EquipoNombre
    categoria: EquipoCategoria
    descripcion: EquipoDescripcion = ""
    descripcion_publica: EquipoPublicoDescripcion = ""
    caracteristicas_tecnicas: EquipoTecnicasCaracteristicas = Field(default_factory=dict)
    url_imagen: EquipoImagenUrl | None = None
    activo: StrictBool = True


class ActualizarEquipo(ModeloApi):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})

    codigo: EquipoCodigo | SkipJsonSchema[None] = None
    nombre: EquipoNombre | SkipJsonSchema[None] = None
    categoria: EquipoCategoria | SkipJsonSchema[None] = None
    descripcion: EquipoDescripcion | SkipJsonSchema[None] = None
    descripcion_publica: EquipoPublicoDescripcion | SkipJsonSchema[None] = None
    caracteristicas_tecnicas: EquipoTecnicasCaracteristicas | SkipJsonSchema[None] = None
    url_imagen: EquipoImagenUrl | None = None
    activo: StrictBool | SkipJsonSchema[None] = None

    @model_validator(mode="after")
    def exigir_no_nulo_cambios(instancia) -> Self:
        if not instancia.model_fields_set:
            raise ValueError("Indica al menos un campo para editar")
        if any(
            getattr(instancia, campo) is None
            for campo in instancia.model_fields_set
            if campo != "url_imagen"
        ):
            raise ValueError("Los campos enviados no pueden ser nulos")
        return instancia


class LecturaEquipo(CrearEquipo):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
