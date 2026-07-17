from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from datetime import datetime

from app.database.base import Base


class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True)
    filename = Column(String(255))
    file_path = Column(String(500))
    status = Column(String(50), default="uploaded")
    project_id = Column(Integer, ForeignKey("projects.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
