"""add chat message status fields and analysis request_id (失败可恢复/幂等)

Revision ID: b8d0e2f4a6c1
Revises: a7c9d1e3f5b7
Create Date: 2026-11-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8d0e2f4a6c1"
down_revision: Union[str, None] = "a7c9d1e3f5b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ok"),
    )
    op.add_column("chat_messages", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("chat_messages", sa.Column("analysis_id", sa.Integer(), nullable=True))
    op.add_column("chat_messages", sa.Column("log_id", sa.Integer(), nullable=True))
    op.add_column("analyses", sa.Column("request_id", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_analyses_request_id", "analyses", ["request_id"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_analyses_request_id", table_name="analyses")
    op.drop_column("analyses", "request_id")
    op.drop_column("chat_messages", "log_id")
    op.drop_column("chat_messages", "analysis_id")
    op.drop_column("chat_messages", "error_message")
    op.drop_column("chat_messages", "status")
