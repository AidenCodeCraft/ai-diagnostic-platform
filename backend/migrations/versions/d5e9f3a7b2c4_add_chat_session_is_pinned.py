"""add chat session is_pinned

Revision ID: d5e9f3a7b2c4
Revises: c4d8e2f6a1b3
Create Date: 2026-11-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e9f3a7b2c4"
down_revision: Union[str, None] = "c4d8e2f6a1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "is_pinned")
