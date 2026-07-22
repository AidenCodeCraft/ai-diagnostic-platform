"""Login attempt tracking model for brute-force protection."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String

from app.database.base import Base


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True)
    mac_address = Column(String(17), nullable=False, index=True)  # XX:XX:XX:XX:XX:XX
    username = Column(String(50), nullable=False)
    attempt_count = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)  # None = not locked
    cycle_phase = Column(Integer, default=0)  # 0=initial, 1=cycle(1h lock + 1 try)
    last_attempt_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
