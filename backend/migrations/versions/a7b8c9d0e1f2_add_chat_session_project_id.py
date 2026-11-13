"""add chat_sessions.project_id

Revision ID: a7b8c9d0e1f2
Revises: f3a4b5c6d7e8
Create Date: 2026-11-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "project_id")
