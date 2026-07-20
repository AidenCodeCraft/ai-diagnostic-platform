"""add logs fields and agent_tasks table

Revision ID: a1b2c3d4e5f6
Revises: f3e2d5b6a1c2
Create Date: 2026-07-20 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f3e2d5b6a1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing columns to logs table
    op.add_column("logs", sa.Column("device", sa.String(length=100), nullable=True))
    op.add_column("logs", sa.Column("version", sa.String(length=50), nullable=True))
    op.add_column("logs", sa.Column("description", sa.String(length=500), nullable=True))

    # Create agent_tasks table
    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(length=100), nullable=False),
        sa.Column("log_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("steps", sa.Text(), nullable=True),
        sa.Column("tool_plan", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["log_id"], ["logs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )


def downgrade() -> None:
    op.drop_table("agent_tasks")
    op.drop_column("logs", "description")
    op.drop_column("logs", "version")
    op.drop_column("logs", "device")
