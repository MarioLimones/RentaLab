"""Persist users and add nullable authorship without guessing historical owners.

Revision ID: 0006_users_ownership
Revises: 0005_auth_sessions
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_users_ownership"
down_revision = "0005_auth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(1024), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name="ck_users_name"),
        sa.CheckConstraint("length(email) BETWEEN 3 AND 254", name="ck_users_email"),
        sa.CheckConstraint("role IN ('customer', 'admin')", name="ck_users_role"),
        sa.CheckConstraint("active IN (0, 1)", name="ck_users_active"),
    )
    # SQLite supports a nullable column with an inline FK. ALTER TABLE avoids copying or
    # dropping referenced business tables, and leaves all historical owners unknown.
    for table, column in (
        ("auth_sessions", "user_id"),
        ("reservations", "customer_user_id"),
        ("incidents", "author_user_id"),
    ):
        op.execute(f"ALTER TABLE {table} ADD COLUMN {column} INTEGER REFERENCES users (id)")
        op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table, column in (
        ("incidents", "author_user_id"),
        ("reservations", "customer_user_id"),
        ("auth_sessions", "user_id"),
    ):
        op.drop_index(f"ix_{table}_{column}", table_name=table)
        op.drop_column(table, column)
    op.drop_table("users")
