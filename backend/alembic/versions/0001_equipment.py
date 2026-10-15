"""Create the physical equipment catalog.

Revision ID: 0001_equipment
Revises:
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_equipment"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equipment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(40, collation="NOCASE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "active",
            sa.Boolean(create_constraint=True, name="ck_equipment_active"),
            nullable=False,
            server_default="1",
        ),
        sa.UniqueConstraint("code", name="uq_equipment_code"),
        sa.CheckConstraint(
            "length(code) BETWEEN 1 AND 40 AND code = upper(trim(code)) "
            "AND code NOT GLOB '*[^A-Z0-9_-]*' AND substr(code, 1, 1) GLOB '[A-Z0-9]'",
            name="ck_equipment_code_canonical",
        ),
        sa.CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name="ck_equipment_name"),
        sa.CheckConstraint("length(trim(category)) BETWEEN 1 AND 80", name="ck_equipment_category"),
        sa.CheckConstraint("length(description) <= 2000", name="ck_equipment_description"),
    )


def downgrade() -> None:
    op.drop_table("equipment")
