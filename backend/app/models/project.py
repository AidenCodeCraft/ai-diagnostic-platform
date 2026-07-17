from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.database.base import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    chip = Column(String(100))
    firmware = Column(String(100))
    owner_id = Column(Integer, ForeignKey("users.id"))

