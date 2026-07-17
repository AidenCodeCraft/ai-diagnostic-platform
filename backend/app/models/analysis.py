from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text

from app.database.base import Base


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True)
    log_id = Column(Integer, ForeignKey("logs.id"))
    result = Column(Text)
    confidence = Column(Float)
    summary = Column(Text)
    root_cause = Column(Text)
    next_steps = Column(Text)
    model = Column(String(100))
