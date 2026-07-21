"""Admin dashboard API — aggregated statistics and system config."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.models.user import User
from app.models.project import Project
from app.models.log import Log
from app.models.analysis import Analysis
from app.models.knowledge import KnowledgeDocument


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """Get aggregated system statistics for the admin dashboard."""
    now = datetime.now(timezone.utc)

    total_users = db.query(func.count(User.id)).scalar() or 0
    total_projects = db.query(func.count(Project.id)).scalar() or 0
    total_logs = db.query(func.count(Log.id)).scalar() or 0
    total_analyses = db.query(func.count(Analysis.id)).scalar() or 0
    total_knowledge = db.query(func.count(KnowledgeDocument.id)).scalar() or 0

    # Analysis success rate
    completed = db.query(func.count(Analysis.id)).filter(Analysis.status == "completed").scalar() or 0
    failed = db.query(func.count(Analysis.id)).filter(Analysis.status == "failed").scalar() or 0

    # Recent 7 days analysis trend
    seven_days_ago = now - timedelta(days=7)
    recent = (
        db.query(func.date(Analysis.created_at), func.count(Analysis.id))
        .filter(Analysis.created_at >= seven_days_ago)
        .group_by(func.date(Analysis.created_at))
        .order_by(func.date(Analysis.created_at))
        .all()
    )
    analysis_trend = [{"date": str(d), "count": c} for d, c in recent]

    # Log storage
    total_log_size = db.query(func.sum(Log.size)).scalar() or 0

    # Active plugins count (placeholder — plugins are in-memory)
    from app.api.plugins import router as plugins_router
    active_plugins = 0  # Will be populated from plugin manager

    return {
        "total_users": total_users,
        "total_projects": total_projects,
        "total_logs": total_logs,
        "total_analyses": total_analyses,
        "total_knowledge": total_knowledge,
        "analysis_completed": completed,
        "analysis_failed": failed,
        "analysis_trend": analysis_trend,
        "total_log_size_bytes": total_log_size,
        "active_plugins": active_plugins,
    }
