from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from rentalab.equipment.models import Equipment


class EquipmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, active: bool | None = None) -> Sequence[Equipment]:
        statement = select(Equipment).order_by(Equipment.code)
        if active is not None:
            statement = statement.where(Equipment.active == active)
        return self.session.scalars(statement).all()

    def get(self, equipment_id: int) -> Equipment | None:
        return self.session.get(Equipment, equipment_id)

    def find_by_code(self, code: str) -> Equipment | None:
        return self.session.scalar(select(Equipment).where(Equipment.code == code))

    def add(self, equipment: Equipment) -> None:
        self.session.add(equipment)

    def commit(self) -> None:
        self.session.commit()
