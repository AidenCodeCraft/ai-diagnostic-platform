from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logging_config import get_logger
from app.database.base import Base
from app.models import User, LoginAttempt, ApiKey  # noqa: F401
from app.models import ChatSession, ChatMessage, AgentTask  # noqa: F401
from app.models import Log, Analysis, Report  # noqa: F401
from app.models import KnowledgeDocument  # noqa: F401
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


def init_db() -> None:
    logger.debug("Initializing database tables...")
    Base.metadata.create_all(bind=engine)


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
    logger.debug("Creating new DB session")
    return SessionLocal()
