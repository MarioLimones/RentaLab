from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from rentalab.database import Base


class SavedProduct(Base):
    __tablename__ = "saved_products"

    customer_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"), primary_key=True)
