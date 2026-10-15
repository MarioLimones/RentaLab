from typing import Literal

from pydantic import BaseModel, Field

from rentalab.reservations.schemas import ReservationRead

ImportRowStatus = Literal["accepted", "already_imported", "rejected"]


class ImportRowResult(BaseModel):
    line: int = Field(ge=2, description="Línea física inicial del registro; cabecera en línea 1")
    external_reference: str | None
    status: ImportRowStatus
    reservation: ReservationRead | None
    message: str


class ImportTotals(BaseModel):
    total: int = Field(ge=0)
    accepted: int = Field(default=0, ge=0)
    already_imported: int = Field(default=0, ge=0)
    rejected: int = Field(default=0, ge=0)


class ImportReport(BaseModel):
    totals: ImportTotals
    rows: list[ImportRowResult]
