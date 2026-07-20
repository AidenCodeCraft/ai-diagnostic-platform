"""add report fields: log_id, title, format, timestamps

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-20 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("log_id", sa.Integer(), nullable=True))
    op.add_column("reports", sa.Column("title", sa.String(length=300), nullable=True))
    op.add_column("reports", sa.Column("format", sa.String(length=20), nullable=True))
    op.add_column("reports", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.add_column("reports", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.create_foreign_key(
        "fk_reports_log_id",
        "reports",
        "logs",
        ["log_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_reports_log_id", "reports", type_="foreignkey")
    op.drop_column("reports", "updated_at")
    op.drop_column("reports", "created_at")
    op.drop_column("reports", "format")
    op.drop_column("reports", "title")
    op.drop_column("reports", "log_id")
