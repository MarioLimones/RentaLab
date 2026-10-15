import re
from datetime import date
from typing import Annotated, Literal, Self

from email_validator import EmailNotValidError, validate_email
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from rentalab.database import SQLITE_MAX_INTEGER
from rentalab.equipment.schemas import EquipmentCode


def require_iso_date(value: object) -> object:
    if type(value) is date:
        return value
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ValueError("Usa una fecha ISO con formato YYYY-MM-DD")
    return value


def normalize_customer_email(value: str) -> str:
    try:
        return validate_email(value, check_deliverability=False, test_environment=True).normalized
    except EmailNotValidError as error:
        raise ValueError("El correo del cliente no es válido") from error


IsoDate = Annotated[date, BeforeValidator(require_iso_date)]
ReservationStatus = Literal["confirmed", "cancelled"]
ReservationOrigin = Literal["portal", "admin", "csv", "legacy"]
ExternalReference = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=120, pattern=r"^[^\x00]*$"
    ),
]
CustomerName = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=120, pattern=r"^[^\x00]*$"
    ),
]
CustomerEmail = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=254),
    AfterValidator(normalize_customer_email),
    Field(json_schema_extra={"format": "email"}),
]


class DateRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: IsoDate = Field(description="Inicio incluido, YYYY-MM-DD")
    end_date: IsoDate = Field(description="Fin excluido, estrictamente posterior al inicio")

    @model_validator(mode="after")
    def require_positive_range(self) -> Self:
        if self.end_date <= self.start_date:
            raise ValueError("La fecha de fin debe ser posterior a la de inicio")
        return self


class ReservationCreate(DateRange):
    equipment_id: Annotated[int, Field(strict=True, gt=0, le=SQLITE_MAX_INTEGER)]
    customer_name: CustomerName
    customer_email: CustomerEmail
    external_reference: ExternalReference | None = None


class ReservationRead(ReservationCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    status: ReservationStatus
    customer_user_id: int | None
    origin: ReservationOrigin


class ReservationByCode(DateRange):
    equipment_code: EquipmentCode
    customer_name: CustomerName
    customer_email: CustomerEmail
    external_reference: ExternalReference


class ReservationFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: Annotated[int, Field(gt=0, le=SQLITE_MAX_INTEGER)] | None = None
    status: ReservationStatus | None = None
    customer: (
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
    customer_user_id: Annotated[int, Field(gt=0, le=SQLITE_MAX_INTEGER)] | None = None
    origin: ReservationOrigin | None = None
    start_date: IsoDate | None = None
    end_date: IsoDate | None = None

    @model_validator(mode="after")
    def require_complete_range(self) -> Self:
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("Envía start_date y end_date juntos para filtrar por intervalo")
        if self.start_date is not None and self.end_date is not None:
            DateRange(start_date=self.start_date, end_date=self.end_date)
        return self


class AvailabilityRead(DateRange):
    equipment_id: int
    available: bool
    reason: Literal["equipment_inactive", "blocking_incident", "reservation_overlap"] | None
    conflicting_reservation_ids: list[int]
