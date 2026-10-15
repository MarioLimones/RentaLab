"""Public product identity while retaining independent physical inventory records."""

from unicodedata import normalize

from sqlalchemy import select
from sqlalchemy.orm import Session

from rentalab.equipment.models import Equipment


def product_key(equipment: Equipment) -> tuple[str, str]:
    # Names describe models; codes continue to identify physical units in administration.
    return tuple(
        normalize("NFC", value.strip()).casefold() for value in (equipment.name, equipment.category)
    )


def active_product_units(session: Session, equipment: Equipment) -> list[Equipment]:
    key = product_key(equipment)
    return [
        item
        for item in session.scalars(
            select(Equipment).where(Equipment.active.is_(True)).order_by(Equipment.id)
        )
        if product_key(item) == key
    ]
