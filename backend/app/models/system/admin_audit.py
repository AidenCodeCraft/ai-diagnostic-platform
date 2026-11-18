from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database.base import Base


class AdminAuditLog(Base):
    """管理后台操作审计记录（谁在什么时间对什么对象做了什么）。"""

    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True)
    operator_id = Column(Integer, nullable=True, index=True)
    operator_name = Column(String(50), nullable=True)
    action = Column(String(50), nullable=False, index=True)  # user.create / config.llm.save ...
    target_type = Column(String(50), nullable=True)          # user / llm_config / system_config / knowledge
    target_id = Column(String(50), nullable=True)
    detail = Column(Text, nullable=True)                     # JSON 字符串，禁止记录密码/密钥
    result = Column(String(20), nullable=False, default="success")  # success / failed
    ip = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
