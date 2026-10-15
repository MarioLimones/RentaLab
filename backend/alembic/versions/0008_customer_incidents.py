"""Link customer reports to known reservations and separate public communication.

Revision ID: 0008_customer_incidents
Revises: 0007_public_catalogue
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_customer_incidents"
down_revision = "0007_public_catalogue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable inline FK avoids reconstructing a referenced table on SQLite. Historical
    # reports retain unknown reservation links; matching an email never establishes ownership.
    op.execute(
        "ALTER TABLE incidents ADD COLUMN reservation_id INTEGER REFERENCES reservations (id)"
    )
    op.create_index("ix_incidents_reservation_id", "incidents", ["reservation_id"])
    # Never copy the previous internal resolution into client-visible communication.
    op.add_column(
        "incidents", sa.Column("public_response", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "incidents", sa.Column("internal_notes", sa.Text(), nullable=False, server_default="")
    )


def downgrade() -> None:
    op.drop_column("incidents", "internal_notes")
    op.drop_column("incidents", "public_response")
    op.drop_index("ix_incidents_reservation_id", table_name="incidents")
    op.drop_column("incidents", "reservation_id")
