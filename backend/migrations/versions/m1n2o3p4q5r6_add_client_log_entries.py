"""add client_log_entries table for frontend client log persistence

Revision ID: m1n2o3p4q5r6
Revises: l1m2n3o4p5q6
Create Date: 2026-07-22 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "m1n2o3p4q5r6"
down_revision: Union[str, None] = "l1m2n3o4p5q6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client_log_entries",
        sa.Column("id", sa.String(64), nullable=False, primary_key=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False, index=True),
        sa.Column("level", sa.Integer(), nullable=False, index=True),
        sa.Column("category", sa.String(32), nullable=False, index=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("tags", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("client_log_entries")
