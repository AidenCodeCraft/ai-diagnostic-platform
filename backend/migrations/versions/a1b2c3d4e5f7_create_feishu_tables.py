"""create feishu event & attachment tables

Revision ID: a1b2c3d4e5f7
Revises: f1a2b3c4d5e6
Create Date: 2026-11-19

飞书图片识别（S1）：事件幂等表 + 图片记录表。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feishu_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=True),
        sa.Column("message_id", sa.String(length=64), nullable=True),
        sa.Column("chat_id", sa.String(length=64), nullable=True),
        sa.Column("sender_id", sa.String(length=64), nullable=True),
        sa.Column("message_type", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="received"),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_feishu_events_event_id", "feishu_events", ["event_id"], unique=True)
    op.create_index("ix_feishu_events_message_id", "feishu_events", ["message_id"])
    op.create_index("ix_feishu_events_created_at", "feishu_events", ["created_at"])

    op.create_table(
        "feishu_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_key", sa.String(length=64), nullable=True),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("image_key", sa.String(length=128), nullable=False),
        sa.Column("chat_id", sa.String(length=64), nullable=True),
        sa.Column("sender_id", sa.String(length=64), nullable=True),
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
        sa.UniqueConstraint("message_id", "image_key", name="uq_feishu_attachment_message_image"),
    )
    op.create_index("ix_feishu_attachments_tenant_key", "feishu_attachments", ["tenant_key"])
    op.create_index("ix_feishu_attachments_status", "feishu_attachments", ["status"])
    op.create_index("ix_feishu_attachments_sha256", "feishu_attachments", ["sha256"])
    op.create_index("ix_feishu_attachments_created_at", "feishu_attachments", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_feishu_attachments_created_at", table_name="feishu_attachments")
    op.drop_index("ix_feishu_attachments_sha256", table_name="feishu_attachments")
    op.drop_index("ix_feishu_attachments_status", table_name="feishu_attachments")
    op.drop_index("ix_feishu_attachments_tenant_key", table_name="feishu_attachments")
    op.drop_table("feishu_attachments")

    op.drop_index("ix_feishu_events_created_at", table_name="feishu_events")
    op.drop_index("ix_feishu_events_message_id", table_name="feishu_events")
    op.drop_index("ix_feishu_events_event_id", table_name="feishu_events")
    op.drop_table("feishu_events")
