from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator
from pydantic.json_schema import SkipJsonSchema

from rentalab.database import SQLITE_MAX_INTEGER

IncidentPriority = Literal["low", "medium", "high"]
IncidentStatus = Literal["open", "in_progress", "resolved"]
IncidentTitle = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=160, pattern=r"^[^\x00]*$"
    ),
]
IncidentText = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, max_length=2000, pattern=r"^[^\x00]*$"),
]


class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: Annotated[int, Field(strict=True, gt=0, le=SQLITE_MAX_INTEGER)]
    title: IncidentTitle
    description: IncidentText = ""
    priority: IncidentPriority = "medium"
    blocking: StrictBool = False


class IncidentStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: IncidentStatus
    resolution: IncidentText | None = Field(
        default=None,
        description="Explicación no vacía al resolver; omitir o null en otros estados",
    )

    @model_validator(mode="after")
    def require_resolution_only_when_resolving(self) -> Self:
        if self.status == "resolved" and not self.resolution:
            raise ValueError("Resolver exige una explicación no vacía")
        if self.status != "resolved" and self.resolution is not None:
            raise ValueError("La explicación de resolución sólo se admite al resolver")
        return self


class IncidentFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: Annotated[int, Field(gt=0, le=SQLITE_MAX_INTEGER)] | None = None
    status: IncidentStatus | None = None
    priority: IncidentPriority | None = None
    blocking: bool | None = None


class IncidentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})

    priority: IncidentPriority | SkipJsonSchema[None] = None
    blocking: StrictBool | SkipJsonSchema[None] = None
    public_response: IncidentText | SkipJsonSchema[None] = None
    internal_notes: IncidentText | SkipJsonSchema[None] = None

    @model_validator(mode="after")
    def require_non_null_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Indica al menos un campo para editar")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Los campos enviados no pueden ser nulos")
        return self


class IncidentRead(IncidentCreate):
    id: int
    reservation_id: int | None = None
    author_user_id: int | None = None
    status: IncidentStatus
    resolution: IncidentText
    public_response: IncidentText = ""
    internal_notes: IncidentText = ""
    confirmed_reservation_ids: list[int] = Field(
        description="Reservas actualmente confirmadas del equipo; sin filtrar por fecha"
    )
    warning: str | None = Field(description="Aviso calculado; las reservas existentes se conservan")
