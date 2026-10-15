"""Record server-assigned reservation origin without guessing historical sources.

Revision ID: 0009_reservation_origin
Revises: 0008_customer_incidents
"""

from alembic import op

revision = "0009_reservation_origin"
down_revision = "0008_customer_incidents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # An inline CHECK and a constant default let SQLite ALTER the referenced table
    # directly. Known owners and incident reservation FKs remain untouched. Neither
    # email matches nor external references reliably establish a historical source.
    op.execute(
        "ALTER TABLE reservations ADD COLUMN origin VARCHAR(6) NOT NULL "
        "DEFAULT 'legacy' CONSTRAINT ck_reservations_origin "
        "CHECK (origin IN ('portal', 'admin', 'csv', 'legacy'))"
    )


def downgrade() -> None:
    op.drop_column("reservations", "origin")
