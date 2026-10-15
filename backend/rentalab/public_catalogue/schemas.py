from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from rentalab.reservations.schemas import DateRange, IsoDate

SearchText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=120, pattern=r"^[^\x00]*$"),
]
CategoryFilter = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=80, pattern=r"^[^\x00]*$"),
]


class PublicCatalogueFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: SearchText | None = Field(
        default=None,
        description="Fragmento literal del nombre, sin distinguir mayúsculas y minúsculas",
    )
    category: CategoryFilter | None = Field(
        default=None,
        description="Categoría exacta, sin distinguir mayúsculas y minúsculas",
    )


class PublicDateRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: IsoDate | None = Field(default=None, description="Inicio incluido, YYYY-MM-DD")
    end_date: IsoDate | None = Field(default=None, description="Fin excluido, YYYY-MM-DD")

    @model_validator(mode="after")
    def require_complete_positive_range(self) -> Self:
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("Envía start_date y end_date juntos para consultar disponibilidad")
        if self.start_date is not None and self.end_date is not None:
            DateRange(start_date=self.start_date, end_date=self.end_date)
        return self

    def to_date_range(self) -> DateRange | None:
        if self.start_date is None or self.end_date is None:
            return None
        return DateRange(start_date=self.start_date, end_date=self.end_date)


class PublicEquipmentRead(BaseModel):
    """Allowlist: administrative serializers must never serve the public catalogue."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    category: str
    public_description: str
    technical_specs: dict[str, str]
    image_url: str | None
    image_fallback_url: str = Field(description="Imagen local disponible sin servicios externos")
    active_reservations_count: int = Field(
        ge=0,
        description=(
            "Reservas confirmadas en curso o futuras de las unidades activas del modelo. "
            "No incluye canceladas ni las que terminan hoy en Europe/Madrid (fin excluido)."
        ),
    )


class PublicAvailabilityRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: int
    start_date: IsoDate | None
    end_date: IsoDate | None
    available: bool | None = Field(
        description="null sin fechas; orientativa, se vuelve a comprobar al confirmar una reserva"
    )
    status: Literal["select_dates", "available", "unavailable"]


class PublicReservationsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublicReservationsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: int
    reservations: list[DateRange] = Field(
        description=(
            "Fechas originales [inicio, fin) de cada reserva confirmada en curso o futura, "
            "ordenadas por inicio y fin, sin agrupar, recortar ni revelar datos privados. "
            "Se excluyen las que terminan hoy en Europe/Madrid."
        )
    )


class PublicCalendarRange(DateRange):
    @model_validator(mode="after")
    def limit_calendar_window(self) -> Self:
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("El calendario admite como máximo 366 días por consulta")
        return self


class PublicCalendarRead(PublicCalendarRange):
    equipment_id: int
    occupied_ranges: list[DateRange] = Field(
        description="Días ocupados [inicio, fin), agrupados y recortados al rango consultado"
    )
    can_book: bool = Field(
        description=(
            "El equipo admite reservas; los rangos ocupados siguen sin estar disponibles. "
            "La confirmación vuelve a comprobar las reglas de forma atómica."
        )
    )
    unavailable_end_dates: list[IsoDate] = Field(
        default_factory=list,
        description="Devoluciones sin una unidad libre para todo el intervalo desde booking_start",
    )


class PublicCalendarQuery(PublicCalendarRange):
    booking_start: IsoDate | None = Field(
        default=None, description="Recogida seleccionada para comprobar devoluciones del calendario"
    )

    @model_validator(mode="after")
    def limit_booking_window(self) -> Self:
        if self.booking_start is not None and (self.end_date - self.booking_start).days > 366:
            raise ValueError("El calendario admite como máximo 366 días desde la recogida")
        return self
