"""Add explicit public presentation fields without publishing existing notes.

Revision ID: 0007_public_catalogue
Revises: 0006_users_ownership
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_public_catalogue"
down_revision = "0006_users_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADD COLUMN keeps physical-unit IDs, references and all existing values intact.
    # In particular, the previous description is internal and must never be copied here.
    op.add_column(
        "equipment", sa.Column("public_description", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "equipment", sa.Column("technical_specs", sa.JSON(), nullable=False, server_default="{}")
    )
    op.add_column("equipment", sa.Column("image_url", sa.String(2048), nullable=True))


def downgrade() -> None:
    op.drop_column("equipment", "image_url")
    op.drop_column("equipment", "technical_specs")
    op.drop_column("equipment", "public_description")
