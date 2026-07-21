"""add parent_id to knowledge_documents for folder hierarchy

Revision ID: k1l2m3n4o5p6
Revises: j1k2l3m4n5o6
Create Date: 2026-07-21 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, None] = "j1k2l3m4n5o6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_knowledge_parent_id",
        "knowledge_documents",
        "knowledge_documents",
        ["parent_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_knowledge_parent_id", "knowledge_documents", type_="foreignkey")
    op.drop_column("knowledge_documents", "parent_id")
