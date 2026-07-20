"""add agent task timestamps and error_message

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-20 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_tasks", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("agent_tasks", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.add_column("agent_tasks", sa.Column("updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_tasks", "updated_at")
    op.drop_column("agent_tasks", "created_at")
    op.drop_column("agent_tasks", "error_message")
