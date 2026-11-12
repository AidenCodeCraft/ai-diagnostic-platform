"""add log_events table

Revision ID: f3a4b5c6d7e8
Revises: e2b3c4d5f6a7
Create Date: 2026-11-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "e2b3c4d5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "log_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("log_id", sa.Integer(), sa.ForeignKey("logs.id"), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.Column("level", sa.String(20), server_default="INFO"),
        sa.Column("module", sa.String(100), server_default="system"),
        sa.Column("source_type", sa.String(50), server_default="generic"),
        sa.Column("is_error", sa.Boolean(), server_default=sa.false()),
        sa.Column("classification", sa.String(100), server_default="unknown"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("raw", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_log_events_log_id", "log_events", ["log_id"])


def downgrade() -> None:
    op.drop_index("ix_log_events_log_id", table_name="log_events")
    op.drop_table("log_events")
