from sqlalchemy import Column, Integer, String, Text

from app.database.base import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True)
    title = Column(String(200))
    category = Column(String(100))
    content = Column(Text)
    vector_id = Column(String(200))
