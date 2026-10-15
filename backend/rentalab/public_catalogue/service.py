from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from rentalab.availability import AvailabilityService
from rentalab.clock import TodayProvider, madrid_today
from rentalab.equipment.groups import active_product_units, product_key
from rentalab.equipment.models import Equipment
from rentalab.equipment.service import EquipmentNotFound
from rentalab.public_catalogue.schemas import (
    PublicAvailabilityRead,
    PublicCalendarQuery,
    PublicCalendarRead,
    PublicCatalogueFilters,
    PublicDateRange,
    PublicEquipmentRead,
    PublicReservationsRead,
)
from rentalab.reservations.repository import ReservationRepository
from rentalab.reservations.schemas import DateRange

IMAGE_FALLBACK_URL = "/api/public/images/equipment-placeholder.svg"


def public_equipment(equipment: Equipment, active_reservations_count: int) -> PublicEquipmentRead:
    # Explicit field assignment also protects administrative callers of the public API.
    return PublicEquipmentRead(
        id=equipment.id,
        name=equipment.name,
        category=equipment.category,
        public_description=equipment.public_description,
        technical_specs=equipment.technical_specs,
        image_url=equipment.image_url,
        image_fallback_url=IMAGE_FALLBACK_URL,
        active_reservations_count=active_reservations_count,
    )


class PublicCatalogueService:
    def __init__(self, session: Session, today: TodayProvider = madrid_today) -> None:
        self.session = session
        self.today = today
        self.reservations = ReservationRepository(session)
        self.availability = AvailabilityService(self.reservations)

    def list(self, filters: PublicCatalogueFilters) -> list[PublicEquipmentRead]:
        equipment = self.session.scalars(
            select(Equipment).where(Equipment.active.is_(True)).order_by(Equipment.id)
        ).all()
        counts = self.reservations.active_counts_by_equipment(
            [item.id for item in equipment], self.today()
        )
        query = (filters.q or "").casefold()
        category = (filters.category or "").casefold()
        # SQLite NOCASE is ASCII-only. Casefold preserves Unicode names/categories,
        # while literal Python comparisons never turn % or _ into SQL wildcards.
        products: dict[tuple[str, str], Equipment] = {}
        product_counts: dict[tuple[str, str], int] = {}
        for item in equipment:
            key = product_key(item)
            products.setdefault(key, item)
            product_counts[key] = product_counts.get(key, 0) + counts.get(item.id, 0)
        return [
            public_equipment(item, product_counts[product_key(item)])
            for item in sorted(products.values(), key=lambda item: (item.name, item.id))
            if (not query or query in item.name.casefold())
            and (not category or category == item.category.casefold())
        ]

    def get_active(self, equipment_id: int) -> Equipment:
        equipment = self.session.get(Equipment, equipment_id)
        if equipment is None or not equipment.active:
            raise EquipmentNotFound
        return equipment

    def get(self, equipment_id: int) -> PublicEquipmentRead:
        equipment = self.get_active(equipment_id)
        units = active_product_units(self.session, equipment)
        counts = self.reservations.active_counts_by_equipment(
            [unit.id for unit in units], self.today()
        )
        return public_equipment(units[0], sum(counts.values()))

    def check_availability(
        self, equipment_id: int, dates: PublicDateRange
    ) -> PublicAvailabilityRead:
        equipment = self.get_active(equipment_id)
        date_range = dates.to_date_range()
        if date_range is None:
            return PublicAvailabilityRead(
                equipment_id=equipment_id,
                start_date=None,
                end_date=None,
                available=None,
                status="select_dates",
            )
        available = any(
            self.availability.check(unit.id, date_range).available
            for unit in active_product_units(self.session, equipment)
        )
        # Reasons, incident details and reservation identifiers remain private.
        return PublicAvailabilityRead(
            equipment_id=equipment_id,
            start_date=date_range.start_date,
            end_date=date_range.end_date,
            available=available,
            status="available" if available else "unavailable",
        )

    def reservation_dates(self, equipment_id: int) -> PublicReservationsRead:
        equipment = self.get_active(equipment_id)
        units = active_product_units(self.session, equipment)
        ranges = self.reservations.active_date_ranges([unit.id for unit in units], self.today())
        return PublicReservationsRead(
            equipment_id=units[0].id,
            reservations=[DateRange(start_date=start, end_date=end) for start, end in ranges],
        )

    def calendar(self, equipment_id: int, dates: PublicCalendarQuery) -> PublicCalendarRead:
        equipment = self.get_active(equipment_id)
        repository = ReservationRepository(self.session)
        units = [
            unit
            for unit in active_product_units(self.session, equipment)
            if not repository.has_blocking_incident(unit.id)
        ]
        query_start = min(dates.start_date, dates.booking_start or dates.start_date)
        unit_ranges = [
            repository.occupied_ranges(unit.id, query_start, dates.end_date) for unit in units
        ]
        occupied: list[DateRange] = []
        unavailable_end_dates = []
        day = dates.start_date
        while day < dates.end_date:
            # A day is occupied only when every usable unit is booked that day.
            if unit_ranges and all(
                any(start <= day < end for start, end in ranges) for ranges in unit_ranges
            ):
                next_day = day + timedelta(days=1)
                if occupied and occupied[-1].end_date == day:
                    occupied[-1] = DateRange(start_date=occupied[-1].start_date, end_date=next_day)
                else:
                    occupied.append(DateRange(start_date=day, end_date=next_day))
            # Return dates require one physical unit free throughout the selected period.
            if (
                dates.booking_start is not None
                and day > dates.booking_start
                and not any(
                    not any(start < day and end > dates.booking_start for start, end in ranges)
                    for ranges in unit_ranges
                )
            ):
                unavailable_end_dates.append(day)
            day += timedelta(days=1)
        return PublicCalendarRead(
            equipment_id=equipment_id,
            start_date=dates.start_date,
            end_date=dates.end_date,
            occupied_ranges=occupied,
            can_book=bool(units),
            unavailable_end_dates=unavailable_end_dates,
        )
