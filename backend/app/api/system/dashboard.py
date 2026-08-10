"""Dashboard / Statistics API endpoint."""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.auth import User
from app.models.chat import ChatSession, ChatMessage
from app.models.diagnostics import Log, Analysis
from app.models.knowledge import KnowledgeDocument
from app.models.system import Project

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/statistics")
def get_statistics(
    days: int = 7,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    获取 Dashboard 统计数据

    Query params:
        days: 趋势统计的天数（默认 7 天）
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    # ── 基础统计 ──
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_projects = db.query(func.count(Project.id)).scalar() or 0
    total_logs = db.query(func.count(Log.id)).scalar() or 0
    total_analyses = db.query(func.count(Analysis.id)).scalar() or 0
    total_knowledge = db.query(func.count(KnowledgeDocument.id)).scalar() or 0
    total_sessions = db.query(func.count(ChatSession.id)).scalar() or 0
    total_messages = db.query(func.count(ChatMessage.id)).scalar() or 0

    # ── 分析任务统计 ──
    analysis_completed = db.query(func.count(Analysis.id)).filter(
        Analysis.status == "completed"
    ).scalar() or 0
    analysis_failed = db.query(func.count(Analysis.id)).filter(
        Analysis.status == "failed"
    ).scalar() or 0

    # ── 存储统计 ──
    total_log_size_bytes = db.query(func.coalesce(func.sum(Log.size), 0)).scalar() or 0

    # ── 趋势数据（近 N 天每日分析数） ──
    trend_query = (
        db.query(
            func.date(Analysis.created_at).label("date"),
            func.count(Analysis.id).label("count"),
        )
        .filter(Analysis.created_at >= since)
        .group_by(func.date(Analysis.created_at))
        .order_by("date")
        .all()
    )
    analysis_trend = [
        {"date": str(row.date), "count": row.count}
        for row in trend_query
    ]

    # ── 填充缺失日期 ──
    date_set = {row["date"] for row in analysis_trend}
    for i in range(days):
        d = (since + timedelta(days=i)).strftime("%Y-%m-%d")
        if d not in date_set:
            analysis_trend.append({"date": d, "count": 0})
    analysis_trend.sort(key=lambda x: x["date"])

    # ── 活跃用户（近 30 天有登录/消息的用户） ──
    thirty_days_ago = now - timedelta(days=30)
    active_users = (
        db.query(func.count(func.distinct(ChatMessage.role == "user" and ChatMessage.session_id)))
        .filter(ChatMessage.created_at >= thirty_days_ago)
        .scalar()
    ) or 0

    # ── 知识库分类统计 ──
    kb_categories = (
        db.query(
            KnowledgeDocument.category,
            func.count(KnowledgeDocument.id).label("count"),
        )
        .group_by(KnowledgeDocument.category)
        .all()
    )
    knowledge_by_category = [
        {"category": row.category or "未分类", "count": row.count}
        for row in kb_categories
    ]

    return {
        # 基础统计
        "total_users": total_users,
        "total_projects": total_projects,
        "total_logs": total_logs,
        "total_analyses": total_analyses,
        "total_knowledge": total_knowledge,
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        # 分析统计
        "analysis_completed": analysis_completed,
        "analysis_failed": analysis_failed,
        "analysis_success_rate": (
            round(analysis_completed / total_analyses * 100, 1)
            if total_analyses > 0
            else 0
        ),
        # 存储
        "total_log_size_bytes": total_log_size_bytes,
        "total_log_size_mb": round(total_log_size_bytes / (1024 * 1024), 2),
        # 趋势
        "analysis_trend": analysis_trend,
        "trend_days": days,
        # 活跃度
        "active_users_30d": active_users,
        # 知识库
        "knowledge_by_category": knowledge_by_category,
    }
