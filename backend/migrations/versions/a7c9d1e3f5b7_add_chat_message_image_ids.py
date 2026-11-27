"""add chat_message image_ids (截图随消息持久化)

Revision ID: a7c9d1e3f5b7
Revises: c1d2e3f4a5b6
Create Date: 2026-11-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c9d1e3f5b7"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("image_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "image_ids")
