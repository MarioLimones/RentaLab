from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from rentalab.base_datos import Base


class Usuario(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name="ck_users_name"),
        CheckConstraint("length(email) BETWEEN 3 AND 254", name="ck_users_email"),
        CheckConstraint("role IN ('customer', 'admin')", name="ck_users_role"),
        CheckConstraint("active IN (0, 1)", name="ck_users_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column("name", String(120), nullable=False)
    correo: Mapped[str] = mapped_column("email", String(254), nullable=False, unique=True)
    hash_contrasena: Mapped[str] = mapped_column("password_hash", String(1024), nullable=False)
    rol: Mapped[str] = mapped_column("role", String(16), nullable=False)
    activo: Mapped[bool] = mapped_column("active", Boolean, nullable=False, default=True)


class SesionAutenticacion(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("length(id) = 64", name="ck_auth_sessions_id"),
        CheckConstraint("expires_at > 0", name="ck_auth_sessions_expiry"),
        CheckConstraint(
            "length(credential_version) = 64", name="ck_auth_sessions_credential_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    caduca_en: Mapped[int] = mapped_column("expires_at", Integer, nullable=False, index=True)
    credencial_version: Mapped[str] = mapped_column(
        "credential_version", String(64), nullable=False
    )
    id_usuario: Mapped[int | None] = mapped_column(
        "user_id", ForeignKey("users.id"), nullable=True, index=True
    )
