from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.database.base import Base


class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    status = Column(String(50), default="uploaded")
    project_id = Column(Integer, ForeignKey("projects.id"))
    device = Column(String(100), nullable=True)
    version = Column(String(50), nullable=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
