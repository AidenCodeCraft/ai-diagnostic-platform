"""create knowledge_images table

Revision ID: b7c9d2e4f1a8
Revises: 61fd04709d72
Create Date: 2026-08-13 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c9d2e4f1a8'
down_revision: Union[str, None] = '61fd04709d72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'knowledge_images',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('doc_id', sa.Integer(), sa.ForeignKey('knowledge_documents.id', ondelete='CASCADE'), nullable=True),
        sa.Column('storage_key', sa.String(length=500), nullable=False),
        sa.Column('caption', sa.String(length=500), nullable=True),
        sa.Column('anchor', sa.String(length=300), nullable=True),
        sa.Column('position', sa.Integer(), nullable=True),
        sa.Column('context_text', sa.Text(), nullable=True),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('sha256', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_knowledge_images_doc_id', 'knowledge_images', ['doc_id'])
    op.create_index('ix_knowledge_images_sha256', 'knowledge_images', ['sha256'])


def downgrade() -> None:
    op.drop_index('ix_knowledge_images_sha256', table_name='knowledge_images')
    op.drop_index('ix_knowledge_images_doc_id', table_name='knowledge_images')
    op.drop_table('knowledge_images')
