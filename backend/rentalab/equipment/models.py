from sqlalchemy import JSON, Boolean, CheckConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from rentalab.database import Base


class Equipment(Base):
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
    code: Mapped[str] = mapped_column(String(40, collation="NOCASE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    public_description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    technical_specs: Mapped[dict[str, str]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="ck_equipment_active"),
        nullable=False,
        default=True,
        server_default="1",
    )
