"""create knowledge_image_feedbacks table

Revision ID: c9e4f8a2b6d1
Revises: b7c9d2e4f1a8
Create Date: 2026-08-14 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e4f8a2b6d1'
down_revision: Union[str, None] = 'b7c9d2e4f1a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'knowledge_image_feedbacks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('image_id', sa.Integer(), sa.ForeignKey('knowledge_images.id', ondelete='CASCADE'), nullable=False),
        sa.Column('feedback', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_knowledge_image_feedbacks_image_id', 'knowledge_image_feedbacks', ['image_id'])


def downgrade() -> None:
    op.drop_index('ix_knowledge_image_feedbacks_image_id', table_name='knowledge_image_feedbacks')
    op.drop_table('knowledge_image_feedbacks')
