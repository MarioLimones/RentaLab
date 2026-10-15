from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager

from sqlalchemy import select
from sqlalchemy.orm import Session

from rentalab.database import immediate_transaction
from rentalab.equipment.models import Equipment
from rentalab.incidents.models import Incident
from rentalab.incidents.schemas import IncidentFilters
from rentalab.reservations.models import Reservation


class IncidentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def write_transaction(self) -> AbstractContextManager[None]:
        return immediate_transaction(self.session)

    def get_equipment(self, equipment_id: int) -> Equipment | None:
        return self.session.get(Equipment, equipment_id)

    def get(self, incident_id: int) -> Incident | None:
        return self.session.get(Incident, incident_id)

    def get_owned_reservation(self, reservation_id: int, user_id: int) -> Reservation | None:
        return self.session.scalar(
            select(Reservation).where(
                Reservation.id == reservation_id, Reservation.customer_user_id == user_id
            )
        )

    def get_customer_incident(self, incident_id: int, user_id: int) -> Incident | None:
        return self.session.scalar(
            self._customer_incidents(user_id).where(Incident.id == incident_id)
        )

    def list_customer_incidents(self, user_id: int) -> Sequence[Incident]:
        return self.session.scalars(self._customer_incidents(user_id).order_by(Incident.id)).all()

    @staticmethod
    def _customer_incidents(user_id: int):
        # Authorship alone never makes an unowned or another customer's reservation visible.
        return (
            select(Incident)
            .join(Reservation, Incident.reservation_id == Reservation.id)
            .where(Incident.author_user_id == user_id, Reservation.customer_user_id == user_id)
        )

    def list(self, filters: IncidentFilters) -> Sequence[Incident]:
        statement = select(Incident).order_by(Incident.id)
        if filters.equipment_id is not None:
            statement = statement.where(Incident.equipment_id == filters.equipment_id)
        if filters.status is not None:
            statement = statement.where(Incident.status == filters.status)
        if filters.priority is not None:
            statement = statement.where(Incident.priority == filters.priority)
        if filters.blocking is not None:
            statement = statement.where(Incident.blocking == filters.blocking)
        return self.session.scalars(statement).all()

    def confirmed_reservation_ids(self, equipment_id: int) -> list[int]:
        return list(
            self.session.scalars(
                select(Reservation.id)
                .where(Reservation.equipment_id == equipment_id, Reservation.status == "confirmed")
                .order_by(Reservation.id)
            )
        )

    def add(self, incident: Incident) -> None:
        self.session.add(incident)

    def flush(self) -> None:
        self.session.flush()
