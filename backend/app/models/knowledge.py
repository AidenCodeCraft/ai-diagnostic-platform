from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.database.base import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    category = Column(String(100), nullable=True)
    content = Column(Text, nullable=False)
    source = Column(String(200), nullable=True)
    doc_type = Column(String(50), default="manual")
    parent_id = Column(Integer, ForeignKey("knowledge_documents.id"), nullable=True)  # 文件夹层级
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    status = Column(String(50), default="active")
    vector_id = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
