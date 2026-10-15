import sqlite3
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError

from rentalab.equipment.models import Equipment
from rentalab.equipment.repository import EquipmentRepository
from rentalab.equipment.schemas import EquipmentCreate, EquipmentUpdate


class EquipmentNotFound(Exception):
    pass


class DuplicateEquipmentCode(Exception):
    pass


class EquipmentService:
    def __init__(self, repository: EquipmentRepository) -> None:
        self.repository = repository

    def list(self, active: bool | None = None) -> Sequence[Equipment]:
        return self.repository.list(active)

    def get(self, equipment_id: int) -> Equipment:
        equipment = self.repository.get(equipment_id)
        if equipment is None:
            raise EquipmentNotFound
        return equipment

    def create(self, data: EquipmentCreate) -> Equipment:
        self._ensure_unique_code(data.code)
        equipment = Equipment(**data.model_dump())
        self.repository.add(equipment)
        self._commit()
        return equipment

    def update(self, equipment_id: int, data: EquipmentCreate | EquipmentUpdate) -> Equipment:
        equipment = self.get(equipment_id)
        changes = data.model_dump(exclude_unset=isinstance(data, EquipmentUpdate))
        if "code" in changes:
            self._ensure_unique_code(changes["code"], equipment_id)
        for field, value in changes.items():
            setattr(equipment, field, value)
        self._commit()
        return equipment

    def _ensure_unique_code(self, code: str, equipment_id: int | None = None) -> None:
        existing = self.repository.find_by_code(code)
        if existing is not None and existing.id != equipment_id:
            raise DuplicateEquipmentCode

    def _commit(self) -> None:
        try:
            self.repository.commit()
        except IntegrityError as error:
            self.repository.session.rollback()
            if getattr(error.orig, "sqlite_errorcode", None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE:
                raise DuplicateEquipmentCode from error
            raise
