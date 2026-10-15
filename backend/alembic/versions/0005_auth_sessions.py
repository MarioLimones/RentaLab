"""Add revocable, expiring demonstration operator sessions.

Revision ID: 0005_auth_sessions
Revises: 0004_incidents
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_auth_sessions"
down_revision = "0004_incidents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("credential_version", sa.String(64), nullable=False),
        sa.CheckConstraint("length(id) = 64", name="ck_auth_sessions_id"),
        sa.CheckConstraint("expires_at > 0", name="ck_auth_sessions_expiry"),
        sa.CheckConstraint(
            "length(credential_version) = 64", name="ck_auth_sessions_credential_version"
        ),
    )
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_table("auth_sessions")
