from sqlalchemy import JSON, Boolean, CheckConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from rentalab.base_datos import Base


class Equipo(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        UniqueConstraint("code", name="uq_equipment_code"),
        CheckConstraint(
            "length(code) BETWEEN 1 AND 40 AND code = upper(trim(code)) "
            "AND code NOT GLOB '*[^A-Z0-9_-]*' AND substr(code, 1, 1) GLOB '[A-Z0-9]'",
            name="ck_equipment_code_canonical",
        ),
        CheckConstraint("instr(code, char(0)) = 0", name="ck_equipment_code_no_nul"),
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name="ck_equipment_name"),
        CheckConstraint("length(trim(category)) BETWEEN 1 AND 80", name="ck_equipment_category"),
        CheckConstraint("length(description) <= 2000", name="ck_equipment_description"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column("code", String(40, collation="NOCASE"), nullable=False)
    nombre: Mapped[str] = mapped_column("name", String(120), nullable=False)
    categoria: Mapped[str] = mapped_column("category", String(80), nullable=False)
    descripcion: Mapped[str] = mapped_column(
        "description", Text, nullable=False, default="", server_default=""
    )
    descripcion_publica: Mapped[str] = mapped_column(
        "public_description", Text, nullable=False, default="", server_default=""
    )
    caracteristicas_tecnicas: Mapped[dict[str, str]] = mapped_column(
        "technical_specs", JSON, nullable=False, default=dict, server_default="{}"
    )
    url_imagen: Mapped[str | None] = mapped_column("image_url", String(2048), nullable=True)
    activo: Mapped[bool] = mapped_column(
        "active",
        Boolean(create_constraint=True, name="ck_equipment_active"),
        nullable=False,
        default=True,
        server_default="1",
    )
