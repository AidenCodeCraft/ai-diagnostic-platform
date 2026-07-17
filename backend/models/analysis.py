from sqlalchemy import Column, Integer, Text, Float, ForeignKey

from app.database.base import Base


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True)
    log_id = Column(Integer, ForeignKey("logs.id"))
    result = Column(Text)
    confidence = Column(Float)
