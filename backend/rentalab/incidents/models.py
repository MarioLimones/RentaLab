from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from rentalab.database import Base


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "length(trim(title)) BETWEEN 1 AND 160 AND instr(title, char(0)) = 0",
            name="ck_incidents_title",
        ),
        CheckConstraint(
            "length(description) <= 2000 AND instr(description, char(0)) = 0",
            name="ck_incidents_description",
        ),
        CheckConstraint("priority IN ('low', 'medium', 'high')", name="ck_incidents_priority"),
        CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved')", name="ck_incidents_status"
        ),
        CheckConstraint(
            "((status = 'resolved' AND length(trim(resolution)) BETWEEN 1 AND 2000) "
            "OR (status IN ('open', 'in_progress') AND resolution = '')) "
            "AND instr(resolution, char(0)) = 0",
            name="ck_incidents_resolution",
        ),
        Index("ix_incidents_equipment_blocking_status", "equipment_id", "blocking", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False
    )
    author_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    reservation_id: Mapped[int | None] = mapped_column(
        ForeignKey("reservations.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    priority: Mapped[str] = mapped_column(
        String(6), nullable=False, default="medium", server_default="medium"
    )
    blocking: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="ck_incidents_blocking"),
        nullable=False,
        default=False,
        server_default="0",
    )
    status: Mapped[str] = mapped_column(
        String(11), nullable=False, default="open", server_default="open"
    )
    resolution: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    public_response: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    internal_notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
