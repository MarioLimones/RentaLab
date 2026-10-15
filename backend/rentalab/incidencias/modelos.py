from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from rentalab.base_datos import Base


class Incidencia(Base):
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
    id_equipo: Mapped[int] = mapped_column(
        "equipment_id", ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False
    )
    id_usuario_autor: Mapped[int | None] = mapped_column(
        "author_user_id", ForeignKey("users.id"), nullable=True, index=True
    )
    id_reserva: Mapped[int | None] = mapped_column(
        "reservation_id", ForeignKey("reservations.id"), nullable=True, index=True
    )
    titulo: Mapped[str] = mapped_column("title", String(160), nullable=False)
    descripcion: Mapped[str] = mapped_column(
        "description", Text, nullable=False, default="", server_default=""
    )
    prioridad: Mapped[str] = mapped_column(
        "priority", String(6), nullable=False, default="medium", server_default="medium"
    )
    bloqueante: Mapped[bool] = mapped_column(
        "blocking",
        Boolean(create_constraint=True, name="ck_incidents_blocking"),
        nullable=False,
        default=False,
        server_default="0",
    )
    estado: Mapped[str] = mapped_column(
        "status", String(11), nullable=False, default="open", server_default="open"
    )
    resolucion: Mapped[str] = mapped_column(
        "resolution", Text, nullable=False, default="", server_default=""
    )
    respuesta_publica: Mapped[str] = mapped_column(
        "public_response", Text, nullable=False, default="", server_default=""
    )
    notas_internas: Mapped[str] = mapped_column(
        "internal_notes", Text, nullable=False, default="", server_default=""
    )
