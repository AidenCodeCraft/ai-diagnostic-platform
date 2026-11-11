"""create knowledge_diagnosis_profiles table

Revision ID: d1a2b3c4e5f6
Revises: c9e4f8a2b6d1
Create Date: 2026-11-11 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1a2b3c4e5f6'
down_revision: Union[str, None] = 'c9e4f8a2b6d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'knowledge_diagnosis_profiles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('doc_id', sa.Integer(), sa.ForeignKey('knowledge_documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('symptom', sa.Text(), nullable=True),
        sa.Column('environment', sa.String(length=300), nullable=True),
        sa.Column('log_keywords', sa.JSON(), nullable=True),
        sa.Column('log_patterns', sa.JSON(), nullable=True),
        sa.Column('negative_patterns', sa.JSON(), nullable=True),
        sa.Column('expected', sa.Text(), nullable=True),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('solution', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_knowledge_diagnosis_profiles_doc_id', 'knowledge_diagnosis_profiles', ['doc_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_knowledge_diagnosis_profiles_doc_id', table_name='knowledge_diagnosis_profiles')
    op.drop_table('knowledge_diagnosis_profiles')
