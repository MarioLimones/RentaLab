from __future__ import annotations

from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rentalab.base_datos import Base


class Reserva(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        UniqueConstraint("external_reference", name="uq_reservations_external_reference"),
        CheckConstraint("end_date > start_date", name="ck_reservations_positive_range"),
        CheckConstraint("status IN ('confirmed', 'cancelled')", name="ck_reservations_status"),
        CheckConstraint(
            "length(trim(customer_name)) BETWEEN 1 AND 120", name="ck_reservations_customer_name"
        ),
        CheckConstraint(
            "length(customer_email) BETWEEN 1 AND 254", name="ck_reservations_customer_email"
        ),
        CheckConstraint(
            "external_reference IS NULL OR (length(external_reference) BETWEEN 1 AND 120 "
            "AND external_reference = trim(external_reference))",
            name="ck_reservations_external_reference",
        ),
        Index(
            "ix_reservations_equipment_status_dates",
            "equipment_id",
            "status",
            "start_date",
            "end_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_equipo: Mapped[int] = mapped_column(
        "equipment_id", ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False
    )
    id_usuario_cliente: Mapped[int | None] = mapped_column(
        "customer_user_id", ForeignKey("users.id"), nullable=True, index=True
    )
    nombre_cliente: Mapped[str] = mapped_column("customer_name", String(120), nullable=False)
    correo_cliente: Mapped[str] = mapped_column("customer_email", String(254), nullable=False)
    fecha_inicio: Mapped[date] = mapped_column("start_date", Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column("end_date", Date, nullable=False)
    estado: Mapped[str] = mapped_column(
        "status", String(9), nullable=False, default="confirmed", server_default="confirmed"
    )
    referencia_externa: Mapped[str | None] = mapped_column(
        "external_reference", String(120), nullable=True
    )
    origen: Mapped[str] = mapped_column(
        "origin",
        String(6),
        CheckConstraint(
            "origin IN ('portal', 'admin', 'csv', 'legacy')", name="ck_reservations_origin"
        ),
        nullable=False,
        default="legacy",
        server_default="legacy",
    )


class ClienteReservaSolicitud(Base):
    """Solicitud persistente individual o conjunta del cliente autenticado."""

    __tablename__ = "booking_requests"
    __table_args__ = (
        CheckConstraint("length(idempotency_key) = 36", name="ck_booking_requests_key_length"),
        CheckConstraint("end_date > start_date", name="ck_booking_requests_positive_range"),
        CheckConstraint("operation IN ('single', 'batch')", name="ck_booking_requests_operation"),
    )

    id_usuario_cliente: Mapped[int] = mapped_column(
        "customer_user_id", ForeignKey("users.id"), primary_key=True
    )
    clave_idempotencia: Mapped[str] = mapped_column("idempotency_key", String(36), primary_key=True)
    operacion: Mapped[str] = mapped_column("operation", String(6), nullable=False)
    fecha_inicio: Mapped[date] = mapped_column("start_date", Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column("end_date", Date, nullable=False)
    elementos: Mapped[list[ReservaSolicitudReserva]] = relationship(
        cascade="all, delete-orphan", order_by="ReservaSolicitudReserva.posicion"
    )


class ReservaSolicitudReserva(Base):
    """
    Asignaciones originales ordenadas de productos/unidades; metadatos privados de la solicitud.
    """

    __tablename__ = "booking_request_reservations"
    __table_args__ = (
        ForeignKeyConstraint(
            ("customer_user_id", "idempotency_key"),
            ("booking_requests.customer_user_id", "booking_requests.idempotency_key"),
            ondelete="CASCADE",
        ),
        CheckConstraint("position >= 0", name="ck_booking_request_reservations_position"),
        UniqueConstraint("reservation_id", name="uq_booking_request_reservations_reservation"),
    )

    id_usuario_cliente: Mapped[int] = mapped_column("customer_user_id", Integer, primary_key=True)
    clave_idempotencia: Mapped[str] = mapped_column("idempotency_key", String(36), primary_key=True)
    posicion: Mapped[int] = mapped_column("position", Integer, primary_key=True)
    id_equipo_solicitado: Mapped[int] = mapped_column(
        "requested_equipment_id", ForeignKey("equipment.id"), nullable=False
    )
    id_reserva: Mapped[int] = mapped_column(
        "reservation_id", ForeignKey("reservations.id"), nullable=False
    )
    reserva: Mapped[Reserva] = relationship()
