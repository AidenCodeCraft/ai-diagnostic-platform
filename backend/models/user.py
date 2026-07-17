from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime

from app.database.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True)
    password_hash = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
