from sqlalchemy import Column, Integer, Text, ForeignKey

from app.database.base import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id"))
    content = Column(Text)
