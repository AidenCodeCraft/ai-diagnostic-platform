from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logging_config import get_logger
from app.database.base import Base
from app.models import User, LoginAttempt, ApiKey  # noqa: F401
from app.models import ChatSession, ChatMessage, AgentTask  # noqa: F401
from app.models import Log, Analysis, Report  # noqa: F401
from app.models import (  # noqa: F401
    KnowledgeDocument, KnowledgeImage, KnowledgeImageFeedback, KnowledgeDiagnosisProfile,
    KnowledgeSection, KnowledgeDocumentMeta,
)
from app.models import Organization, OrganizationMember, Project, BugCase, ClientLogEntry  # noqa: F401

logger = get_logger(__name__)

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
)
logger.info("Database engine created: %s", settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else "local")

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def _apply_compat_migrations() -> None:
    """兼容性补列：create_all 只建新表，不会给已有表补列。

    对没有 alembic 基线的部署（早期用 create_all 建库）做幂等补列，
    避免新增字段导致线上 500。生产仍建议使用 Alembic 管理迁移。
    """
    from sqlalchemy import inspect, text

    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        if "chat_sessions" in tables:
            columns = {column["name"] for column in inspector.get_columns("chat_sessions")}
            if "project_id" not in columns:
                with engine.begin() as conn:
                    if engine.dialect.name == "postgresql":
                        conn.execute(text(
                            "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS "
                            "project_id INTEGER REFERENCES projects(id)"
                        ))
                    else:
                        conn.execute(text(
                            "ALTER TABLE chat_sessions ADD COLUMN project_id "
                            "INTEGER REFERENCES projects(id)"
                        ))
                logger.info("Applied compatibility migration: chat_sessions.project_id")
    except Exception as exc:  # noqa: BLE001 - 补列失败不阻断启动
        logger.warning("Compatibility migration failed: %s", exc)


def init_db() -> None:
    logger.debug("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    _apply_compat_migrations()


def get_db():
    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory():
    return SessionLocal


def create_session():
    init_db()
    logger.debug("Creating new DB session")
    return SessionLocal()
