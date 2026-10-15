"""Reject embedded NUL characters in equipment codes.

Revision ID: 0002_equipment_code_no_nul
Revises: 0001_equipment
"""

from alembic import op

revision = "0002_equipment_code_no_nul"
down_revision = "0001_equipment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("equipment") as batch_op:
        batch_op.create_check_constraint("ck_equipment_code_no_nul", "instr(code, char(0)) = 0")


def downgrade() -> None:
    with op.batch_alter_table("equipment") as batch_op:
        batch_op.drop_constraint("ck_equipment_code_no_nul", type_="check")
