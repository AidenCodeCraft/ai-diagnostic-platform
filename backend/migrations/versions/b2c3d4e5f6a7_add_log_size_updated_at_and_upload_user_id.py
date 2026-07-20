"""add log size, updated_at, and upload_user_id fields

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-20 09:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("logs", sa.Column("size", sa.Integer(), nullable=True))
    op.add_column("logs", sa.Column("upload_user_id", sa.Integer(), nullable=True))
    op.add_column("logs", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.create_foreign_key(
        "fk_logs_upload_user_id",
        "logs",
        "users",
        ["upload_user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_logs_upload_user_id", "logs", type_="foreignkey")
    op.drop_column("logs", "updated_at")
    op.drop_column("logs", "upload_user_id")
    op.drop_column("logs", "size")
