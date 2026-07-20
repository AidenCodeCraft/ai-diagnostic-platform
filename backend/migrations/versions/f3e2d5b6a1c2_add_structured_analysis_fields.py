"""add structured analysis fields

Revision ID: f3e2d5b6a1c2
Revises: 6ecbd9e1ec74
Create Date: 2026-07-17 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3e2d5b6a1c2"
down_revision: Union[str, None] = "6ecbd9e1ec74"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("analyses", sa.Column("root_cause", sa.Text(), nullable=True))
    op.add_column("analyses", sa.Column("next_steps", sa.Text(), nullable=True))
    op.add_column("analyses", sa.Column("model", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("analyses", "model")
    op.drop_column("analyses", "next_steps")
    op.drop_column("analyses", "root_cause")
    op.drop_column("analyses", "summary")
