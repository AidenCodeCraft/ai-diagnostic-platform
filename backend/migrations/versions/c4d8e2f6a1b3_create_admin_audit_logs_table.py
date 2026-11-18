"""create admin audit logs table

Revision ID: c4d8e2f6a1b3
Revises: b8c1d2e3f4a5
Create Date: 2026-11-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4d8e2f6a1b3"
down_revision: Union[str, None] = "b8c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.Column("operator_name", sa.String(50), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", sa.String(50), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("result", sa.String(20), nullable=False, server_default="success"),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_admin_audit_logs_operator_id", "admin_audit_logs", ["operator_id"])
    op.create_index("ix_admin_audit_logs_action", "admin_audit_logs", ["action"])
    op.create_index("ix_admin_audit_logs_created_at", "admin_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_logs_created_at", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_action", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_operator_id", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
