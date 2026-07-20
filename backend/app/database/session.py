from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.database.base import Base
from app.models import log, project, user, analysis, report, knowledge  # noqa: F401
from app.models.agent_task import AgentTask  # noqa: F401


engine = create_engine(
    settings.DATABASE_URL,
    echo=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def init_db() -> None:
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
    return SessionLocal()
