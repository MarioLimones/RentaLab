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

from rentalab.database import Base


class Reservation(Base):
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
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False
    )
    customer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(254), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(9), nullable=False, default="confirmed", server_default="confirmed"
    )
    external_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    origin: Mapped[str] = mapped_column(
        String(6),
        CheckConstraint(
            "origin IN ('portal', 'admin', 'csv', 'legacy')", name="ck_reservations_origin"
        ),
        nullable=False,
        default="legacy",
        server_default="legacy",
    )


class CustomerBookingRequest(Base):
    """A durable single or batch intent, scoped to the authenticated customer."""

    __tablename__ = "booking_requests"
    __table_args__ = (
        CheckConstraint("length(idempotency_key) = 36", name="ck_booking_requests_key_length"),
        CheckConstraint("end_date > start_date", name="ck_booking_requests_positive_range"),
        CheckConstraint("operation IN ('single', 'batch')", name="ck_booking_requests_operation"),
    )

    customer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(36), primary_key=True)
    operation: Mapped[str] = mapped_column(String(6), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    items: Mapped[list[BookingRequestReservation]] = relationship(
        cascade="all, delete-orphan", order_by="BookingRequestReservation.position"
    )


class BookingRequestReservation(Base):
    """Ordered original product/unit assignments; private request metadata only."""

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

    customer_user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(36), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    requested_equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"), nullable=False)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("reservations.id"), nullable=False)
    reservation: Mapped[Reservation] = relationship()
