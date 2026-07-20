"""add knowledge document fields: source, doc_type, project_id, status, timestamps

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-20 10:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("source", sa.String(length=200), nullable=True))
    op.add_column("knowledge_documents", sa.Column("doc_type", sa.String(length=50), nullable=True))
    op.add_column("knowledge_documents", sa.Column("project_id", sa.Integer(), nullable=True))
    op.add_column("knowledge_documents", sa.Column("status", sa.String(length=50), nullable=True))
    op.add_column("knowledge_documents", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.add_column("knowledge_documents", sa.Column("updated_at", sa.DateTime(), nullable=True))

    op.create_foreign_key(
        "fk_knowledge_project_id",
        "knowledge_documents",
        "projects",
        ["project_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_knowledge_project_id", "knowledge_documents", type_="foreignkey")
    op.drop_column("knowledge_documents", "updated_at")
    op.drop_column("knowledge_documents", "created_at")
    op.drop_column("knowledge_documents", "status")
    op.drop_column("knowledge_documents", "project_id")
    op.drop_column("knowledge_documents", "doc_type")
    op.drop_column("knowledge_documents", "source")
