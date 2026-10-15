from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from rentalab.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name="ck_users_name"),
        CheckConstraint("length(email) BETWEEN 3 AND 254", name="ck_users_email"),
        CheckConstraint("role IN ('customer', 'admin')", name="ck_users_role"),
        CheckConstraint("active IN (0, 1)", name="ck_users_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(1024), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("length(id) = 64", name="ck_auth_sessions_id"),
        CheckConstraint("expires_at > 0", name="ck_auth_sessions_expiry"),
        CheckConstraint(
            "length(credential_version) = 64", name="ck_auth_sessions_credential_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    credential_version: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
