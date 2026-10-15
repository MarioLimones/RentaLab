from rentalab.equipment.service import EquipmentNotFound
from rentalab.incidents.models import Incident
from rentalab.incidents.repository import IncidentRepository
from rentalab.incidents.schemas import (
    IncidentCreate,
    IncidentFilters,
    IncidentRead,
    IncidentStatusChange,
    IncidentUpdate,
)


class IncidentNotFound(Exception):
    pass


class IncidentConflict(Exception):
    pass


ALLOWED_TRANSITIONS = {
    "open": frozenset({"in_progress", "resolved"}),
    "in_progress": frozenset({"resolved"}),
    "resolved": frozenset(),
}


class IncidentService:
    def __init__(self, repository: IncidentRepository) -> None:
        self.repository = repository

    def get(self, incident_id: int) -> IncidentRead:
        return self._read(self._get_incident(incident_id))

    def list(self, filters: IncidentFilters) -> list[IncidentRead]:
        if (
            filters.equipment_id is not None
            and self.repository.get_equipment(filters.equipment_id) is None
        ):
            raise EquipmentNotFound
        return [self._read(incident) for incident in self.repository.list(filters)]

    def create(self, data: IncidentCreate, *, author_user_id: int | None = None) -> IncidentRead:
        with self.repository.write_transaction():
            if self.repository.get_equipment(data.equipment_id) is None:
                raise EquipmentNotFound
            incident = Incident(
                **data.model_dump(), status="open", resolution="", author_user_id=author_user_id
            )
            self.repository.add(incident)
            self.repository.flush()
            response = self._read(incident)
        return response

    def change_status(self, incident_id: int, data: IncidentStatusChange) -> IncidentRead:
        with self.repository.write_transaction():
            incident = self._get_incident(incident_id)
            if data.status not in ALLOWED_TRANSITIONS[incident.status]:
                raise IncidentConflict(f"No se permite pasar de {incident.status} a {data.status}")
            incident.status = data.status
            incident.resolution = data.resolution or ""
            self.repository.flush()
            response = self._read(incident)
        return response

    def update(self, incident_id: int, data: IncidentUpdate) -> IncidentRead:
        # Management changes share the reservation writer lock: a blocking decision and
        # a booking cannot both decide from an earlier, unlocked availability snapshot.
        with self.repository.write_transaction():
            incident = self._get_incident(incident_id)
            for field, value in data.model_dump(exclude_unset=True).items():
                setattr(incident, field, value)
            self.repository.flush()
            response = self._read(incident)
        return response

    def _get_incident(self, incident_id: int) -> Incident:
        incident = self.repository.get(incident_id)
        if incident is None:
            raise IncidentNotFound
        return incident

    def _read(self, incident: Incident) -> IncidentRead:
        confirmed_ids = self.repository.confirmed_reservation_ids(incident.equipment_id)
        return IncidentRead(
            id=incident.id,
            reservation_id=incident.reservation_id,
            author_user_id=incident.author_user_id,
            equipment_id=incident.equipment_id,
            title=incident.title,
            description=incident.description,
            priority=incident.priority,
            blocking=incident.blocking,
            status=incident.status,
            resolution=incident.resolution,
            public_response=incident.public_response,
            internal_notes=incident.internal_notes,
            confirmed_reservation_ids=confirmed_ids,
            warning=(
                "El equipo tiene reservas confirmadas. "
                "La incidencia no las cancela ni las modifica."
                if confirmed_ids
                else None
            ),
        )
