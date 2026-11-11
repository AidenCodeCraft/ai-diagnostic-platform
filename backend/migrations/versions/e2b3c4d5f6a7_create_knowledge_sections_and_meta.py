"""create knowledge_sections and knowledge_document_metas tables

Revision ID: e2b3c4d5f6a7
Revises: d1a2b3c4e5f6
Create Date: 2026-11-11 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2b3c4d5f6a7'
down_revision: Union[str, None] = 'd1a2b3c4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'knowledge_sections',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('doc_id', sa.Integer(), sa.ForeignKey('knowledge_documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('section_key', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('level', sa.Integer(), nullable=True),
        sa.Column('start_line', sa.Integer(), nullable=True),
        sa.Column('end_line', sa.Integer(), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('position', sa.Integer(), nullable=True),
    )
    op.create_index('ix_knowledge_sections_doc_id', 'knowledge_sections', ['doc_id'])

    op.create_table(
        'knowledge_document_metas',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('doc_id', sa.Integer(), sa.ForeignKey('knowledge_documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('quality_score', sa.Float(), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('template_key', sa.String(length=50), nullable=True),
        sa.Column('features', sa.JSON(), nullable=True),
        sa.Column('normalized_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_knowledge_document_metas_doc_id', 'knowledge_document_metas', ['doc_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_knowledge_document_metas_doc_id', table_name='knowledge_document_metas')
    op.drop_table('knowledge_document_metas')
    op.drop_index('ix_knowledge_sections_doc_id', table_name='knowledge_sections')
    op.drop_table('knowledge_sections')
