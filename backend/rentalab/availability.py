from rentalab.equipment.service import EquipmentNotFound
from rentalab.reservations.repository import ReservationRepository
from rentalab.reservations.schemas import AvailabilityRead, DateRange


class AvailabilityService:
    """One availability policy for queries and all reservation creation paths."""

    def __init__(self, repository: ReservationRepository) -> None:
        self.repository = repository

    def check(self, equipment_id: int, date_range: DateRange) -> AvailabilityRead:
        equipment = self.repository.get_equipment(equipment_id)
        if equipment is None:
            raise EquipmentNotFound
        conflicts: list[int] = []
        if not equipment.active:
            reason = "equipment_inactive"
        elif self.repository.has_blocking_incident(equipment_id):
            reason = "blocking_incident"
        else:
            conflicts = self.repository.conflicting_ids(
                equipment_id, date_range.start_date, date_range.end_date
            )
            reason = "reservation_overlap" if conflicts else None
        return AvailabilityRead(
            equipment_id=equipment_id,
            **date_range.model_dump(),
            available=reason is None,
            reason=reason,
            conflicting_reservation_ids=conflicts,
        )
