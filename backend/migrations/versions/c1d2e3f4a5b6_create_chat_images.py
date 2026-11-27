"""create chat_images table

Revision ID: c1d2e3f4a5b6
Revises: f1a2b3c4d5e6
Create Date: 2026-11-19

对话界面截图识别（I1）：一次上传一行，识别文本作为现场证据。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("storage_ref", sa.String(length=512), nullable=True),
        sa.Column("mime", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("recognize_path", sa.String(length=16), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_chat_images_session_id", "chat_images", ["session_id"])
    op.create_index("ix_chat_images_user_id", "chat_images", ["user_id"])
    op.create_index("ix_chat_images_sha256", "chat_images", ["sha256"])
    op.create_index("ix_chat_images_status", "chat_images", ["status"])
    op.create_index("ix_chat_images_created_at", "chat_images", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_images_created_at", table_name="chat_images")
    op.drop_index("ix_chat_images_status", table_name="chat_images")
    op.drop_index("ix_chat_images_sha256", table_name="chat_images")
    op.drop_index("ix_chat_images_user_id", table_name="chat_images")
    op.drop_index("ix_chat_images_session_id", table_name="chat_images")
    op.drop_table("chat_images")
