"""add analysis status, timestamps, and error_message fields

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-20 10:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("status", sa.String(length=50), nullable=True))
    op.add_column("analyses", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("analyses", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.add_column("analyses", sa.Column("updated_at", sa.DateTime(), nullable=True))

    # Set default status for existing records
    op.execute("UPDATE analyses SET status = 'completed' WHERE status IS NULL")

    # Make log_id NOT NULL if it wasn't already
    op.alter_column("analyses", "log_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    op.alter_column("analyses", "log_id", existing_type=sa.Integer(), nullable=True)
    op.drop_column("analyses", "updated_at")
    op.drop_column("analyses", "created_at")
    op.drop_column("analyses", "error_message")
    op.drop_column("analyses", "status")
