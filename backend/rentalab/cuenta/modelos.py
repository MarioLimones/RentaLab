from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from rentalab.base_datos import Base


class GuardadosProducto(Base):
    __tablename__ = "saved_products"

    id_usuario_cliente: Mapped[int] = mapped_column(
        "customer_user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    id_equipo: Mapped[int] = mapped_column(
        "equipment_id", ForeignKey("equipment.id"), primary_key=True
    )
