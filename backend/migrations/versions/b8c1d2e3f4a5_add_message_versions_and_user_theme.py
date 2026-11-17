"""add chat message versions and user theme

Revision ID: b8c1d2e3f4a5
Revises: a7b8c9d0e1f2
Create Date: 2026-11-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c1d2e3f4a5"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 编辑重发的版本历史（chat_messages.versions / active_version）
    op.add_column("chat_messages", sa.Column("versions", sa.JSON(), nullable=True))
    op.add_column("chat_messages", sa.Column("active_version", sa.Integer(), nullable=True))
    # 用户主题偏好（users.theme）
    op.add_column("users", sa.Column("theme", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "theme")
    op.drop_column("chat_messages", "active_version")
    op.drop_column("chat_messages", "versions")
