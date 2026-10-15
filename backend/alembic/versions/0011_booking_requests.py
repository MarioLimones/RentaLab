"""Persist customer booking intents and ordered reservations in one transaction.

Revision ID: 0011_booking_requests
Revises: 0010_saved_products
"""

import sqlalchemy as sa

from alembic import op

revision = "0011_booking_requests"
down_revision = "0010_saved_products"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "booking_requests",
        sa.Column("customer_user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=36), primary_key=True),
        sa.Column("operation", sa.String(length=6), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.CheckConstraint("length(idempotency_key) = 36", name="ck_booking_requests_key_length"),
        sa.CheckConstraint("end_date > start_date", name="ck_booking_requests_positive_range"),
        sa.CheckConstraint(
            "operation IN ('single', 'batch')", name="ck_booking_requests_operation"
        ),
    )
    op.create_table(
        "booking_request_reservations",
        sa.Column("customer_user_id", sa.Integer(), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column(
            "requested_equipment_id", sa.Integer(), sa.ForeignKey("equipment.id"), nullable=False
        ),
        sa.Column("reservation_id", sa.Integer(), sa.ForeignKey("reservations.id"), nullable=False),
        sa.ForeignKeyConstraint(
            ("customer_user_id", "idempotency_key"),
            ("booking_requests.customer_user_id", "booking_requests.idempotency_key"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("position >= 0", name="ck_booking_request_reservations_position"),
        sa.UniqueConstraint("reservation_id", name="uq_booking_request_reservations_reservation"),
    )


def downgrade() -> None:
    op.drop_table("booking_request_reservations")
    op.drop_table("booking_requests")
