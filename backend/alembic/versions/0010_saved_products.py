"""Persist account-owned product lists without altering existing business tables.

Revision ID: 0010_saved_products
Revises: 0009_reservation_origin
"""

import sqlalchemy as sa

from alembic import op

revision = "0010_saved_products"
down_revision = "0009_reservation_origin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_products",
        sa.Column(
            "customer_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("equipment_id", sa.Integer(), sa.ForeignKey("equipment.id"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("saved_products")
