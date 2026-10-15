import re
from typing import Annotated, Self
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema


def normalize_code(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


def reject_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("El texto no puede contener NUL")
    return value


EquipmentCode = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9_-]*$"),
    BeforeValidator(normalize_code),
]
EquipmentName = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=120),
    AfterValidator(reject_nul),
]
EquipmentCategory = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=80),
    AfterValidator(reject_nul),
]
EquipmentDescription = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, max_length=2000),
    AfterValidator(reject_nul),
]


def reject_duplicate_spec_names(value: object) -> object:
    if isinstance(value, dict):
        normalized = [key.strip() for key in value if isinstance(key, str)]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Las características no pueden repetir un nombre normalizado")
    return value


def validate_image_url(value: str) -> str:
    if "\\" in value or any(ord(character) <= 32 or ord(character) == 127 for character in value):
        raise ValueError("La imagen debe usar una URL HTTPS o una ruta de imagen pública local")
    try:
        parsed = urlsplit(value)
        # Reading port validates malformed or out-of-range port numbers as well.
        _ = parsed.port
    except ValueError as error:
        raise ValueError("La URL de la imagen no es válida") from error
    if parsed.query or parsed.fragment:
        raise ValueError("La URL de la imagen no admite consulta ni fragmento")
    if (
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
    ):
        return value
    local_prefix = "/api/public/images/"
    if not parsed.scheme and not parsed.netloc and value.startswith(local_prefix):
        segments = value.removeprefix(local_prefix).split("/")
        if all(
            segment not in {".", ".."} and re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", segment)
            for segment in segments
        ):
            return value
    raise ValueError("La imagen debe usar una URL HTTPS o una ruta de imagen pública local")


EquipmentPublicDescription = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, max_length=2000),
    AfterValidator(reject_nul),
]
TechnicalSpecName = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=80),
    AfterValidator(reject_nul),
]
TechnicalSpecValue = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=300),
    AfterValidator(reject_nul),
]
EquipmentTechnicalSpecs = Annotated[
    dict[TechnicalSpecName, TechnicalSpecValue],
    Field(strict=True, max_length=20),
    BeforeValidator(reject_duplicate_spec_names),
]
EquipmentImageUrl = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2048),
    AfterValidator(validate_image_url),
    Field(
        description="URL HTTPS sin credenciales, consulta ni fragmento, o /api/public/images/..."
    ),
]


class EquipmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: EquipmentCode
    name: EquipmentName
    category: EquipmentCategory
    description: EquipmentDescription = ""
    public_description: EquipmentPublicDescription = ""
    technical_specs: EquipmentTechnicalSpecs = Field(default_factory=dict)
    image_url: EquipmentImageUrl | None = None
    active: StrictBool = True


class EquipmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})

    code: EquipmentCode | SkipJsonSchema[None] = None
    name: EquipmentName | SkipJsonSchema[None] = None
    category: EquipmentCategory | SkipJsonSchema[None] = None
    description: EquipmentDescription | SkipJsonSchema[None] = None
    public_description: EquipmentPublicDescription | SkipJsonSchema[None] = None
    technical_specs: EquipmentTechnicalSpecs | SkipJsonSchema[None] = None
    image_url: EquipmentImageUrl | None = None
    active: StrictBool | SkipJsonSchema[None] = None

    @model_validator(mode="after")
    def require_non_null_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Indica al menos un campo para editar")
        if any(
            getattr(self, field) is None for field in self.model_fields_set if field != "image_url"
        ):
            raise ValueError("Los campos enviados no pueden ser nulos")
        return self


class EquipmentRead(EquipmentCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
