"""Add confirmed/cancelled reservations with durable external references.

Revision ID: 0003_reservations
Revises: 0002_equipment_code_no_nul
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_reservations"
down_revision = "0002_equipment_code_no_nul"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("customer_name", sa.String(120), nullable=False),
        sa.Column("customer_email", sa.String(254), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(9), nullable=False, server_default="confirmed"),
        sa.Column("external_reference", sa.String(120), nullable=True),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("external_reference", name="uq_reservations_external_reference"),
        sa.CheckConstraint("end_date > start_date", name="ck_reservations_positive_range"),
        sa.CheckConstraint("status IN ('confirmed', 'cancelled')", name="ck_reservations_status"),
        sa.CheckConstraint(
            "length(trim(customer_name)) BETWEEN 1 AND 120", name="ck_reservations_customer_name"
        ),
        sa.CheckConstraint(
            "length(customer_email) BETWEEN 1 AND 254", name="ck_reservations_customer_email"
        ),
        sa.CheckConstraint(
            "external_reference IS NULL OR (length(external_reference) BETWEEN 1 AND 120 "
            "AND external_reference = trim(external_reference))",
            name="ck_reservations_external_reference",
        ),
    )
    op.create_index(
        "ix_reservations_equipment_status_dates",
        "reservations",
        ["equipment_id", "status", "start_date", "end_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_reservations_equipment_status_dates", table_name="reservations")
    op.drop_table("reservations")
