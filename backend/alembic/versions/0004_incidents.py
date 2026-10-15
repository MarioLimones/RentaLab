"""Add equipment incidents and resolution history without changing reservations.

Revision ID: 0004_incidents
Revises: 0003_reservations
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_incidents"
down_revision = "0003_reservations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("priority", sa.String(6), nullable=False, server_default="medium"),
        sa.Column(
            "blocking",
            sa.Boolean(create_constraint=True, name="ck_incidents_blocking"),
            nullable=False,
            server_default="0",
        ),
        sa.Column("status", sa.String(11), nullable=False, server_default="open"),
        sa.Column("resolution", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "length(trim(title)) BETWEEN 1 AND 160 AND instr(title, char(0)) = 0",
            name="ck_incidents_title",
        ),
        sa.CheckConstraint(
            "length(description) <= 2000 AND instr(description, char(0)) = 0",
            name="ck_incidents_description",
        ),
        sa.CheckConstraint("priority IN ('low', 'medium', 'high')", name="ck_incidents_priority"),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved')", name="ck_incidents_status"
        ),
        sa.CheckConstraint(
            "((status = 'resolved' AND length(trim(resolution)) BETWEEN 1 AND 2000) "
            "OR (status IN ('open', 'in_progress') AND resolution = '')) "
            "AND instr(resolution, char(0)) = 0",
            name="ck_incidents_resolution",
        ),
    )
    op.create_index(
        "ix_incidents_equipment_blocking_status",
        "incidents",
        ["equipment_id", "blocking", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_incidents_equipment_blocking_status", table_name="incidents")
    op.drop_table("incidents")
