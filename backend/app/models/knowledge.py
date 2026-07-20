from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.database.base import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    category = Column(String(100), nullable=True)
    content = Column(Text, nullable=False)
    source = Column(String(200), nullable=True)       # e.g. PDF filename, URL
    doc_type = Column(String(50), default="manual")    # manual, bug_report, faq, datasheet
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    status = Column(String(50), default="active")      # active, archived, draft
    vector_id = Column(String(200), nullable=True)     # placeholder for future Milvus integration
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
