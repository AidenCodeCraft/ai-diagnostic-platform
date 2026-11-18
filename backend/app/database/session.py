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
from app.models import (  # noqa: F401
    Organization, OrganizationMember, Project, BugCase, ClientLogEntry, AdminAuditLog,
)

logger = get_logger(__name__)

engine_kwargs = {}
if not settings.DATABASE_URL.startswith("sqlite"):
    # 高并发下默认池（5+10）不够用；SQLite（测试）不支持这些参数
    engine_kwargs = {
        "pool_size": int(getattr(settings, "DB_POOL_SIZE", 20)),
        "max_overflow": int(getattr(settings, "DB_MAX_OVERFLOW", 60)),
        "pool_recycle": int(getattr(settings, "DB_POOL_RECYCLE", 1800)),
        "pool_pre_ping": True,
    }

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    **engine_kwargs,
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

    # (表名, 列名, 列定义) —— 与 migrations/versions 的增量迁移保持同步
    patches = [
        ("chat_sessions", "project_id", "INTEGER REFERENCES projects(id)"),
        ("chat_sessions", "is_pinned", "BOOLEAN DEFAULT FALSE NOT NULL"),
        ("chat_messages", "versions", "JSON"),
        ("chat_messages", "active_version", "INTEGER"),
        ("users", "theme", "VARCHAR(20)"),
    ]

    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        for table, column, ddl in patches:
            if table not in tables:
                continue
            columns = {c["name"] for c in inspector.get_columns(table)}
            if column in columns:
                continue
            with engine.begin() as conn:
                if engine.dialect.name == "postgresql":
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}"))
                else:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            logger.info("Applied compatibility migration: %s.%s", table, column)
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
