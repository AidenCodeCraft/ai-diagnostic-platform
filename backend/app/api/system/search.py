"""Unified search API across logs, knowledge, analyses, and reports."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.chat import ChatSession, ChatMessage
from app.models.diagnostics import Log, Analysis, Report
from app.models.knowledge import KnowledgeDocument
from app.models.system import BugCase

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def unified_search(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    type: str = Query("all", description="搜索类型: all, logs, knowledge, analyses, reports, bugs, chats"),
    limit: int = Query(20, ge=1, le=100, description="每类返回数量"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    统一搜索接口

    跨多模块搜索，返回分类聚合结果。
    """
    pattern = f"%{q}%"
    result: dict[str, Any] = {"query": q, "type": type}

    def search_logs():
        items = (
            db.query(Log)
            .filter(
                or_(
                    Log.filename.ilike(pattern),
                    Log.device.ilike(pattern),
                )
            )
            .limit(limit)
            .all()
        )
        return [
            {"id": l.id, "filename": l.filename, "status": l.status, "device": l.device}
            for l in items
        ]

    def search_knowledge():
        items = (
            db.query(KnowledgeDocument)
            .filter(
                or_(
                    KnowledgeDocument.title.ilike(pattern),
                    KnowledgeDocument.content.ilike(pattern),
                    KnowledgeDocument.category.ilike(pattern),
                )
            )
            .limit(limit)
            .all()
        )
        return [
            {
                "id": k.id,
                "title": k.title,
                "category": k.category,
                "doc_type": k.doc_type,
                "excerpt": (k.content or "")[:200],
            }
            for k in items
        ]

    def search_analyses():
        items = (
            db.query(Analysis)
            .filter(
                or_(
                    Analysis.summary.ilike(pattern),
                    Analysis.root_cause.ilike(pattern),
                )
            )
            .limit(limit)
            .all()
        )
        return [
            {
                "id": a.id,
                "log_id": a.log_id,
                "status": a.status,
                "summary": (a.summary or "")[:200],
                "confidence": a.confidence,
            }
            for a in items
        ]

    def search_reports():
        items = (
            db.query(Report)
            .filter(Report.summary.ilike(pattern))
            .limit(limit)
            .all()
        )
        return [
            {"id": r.id, "log_id": r.log_id, "analysis_id": r.analysis_id, "summary": (r.summary or "")[:200]}
            for r in items
        ]

    def search_bugs():
        items = (
            db.query(BugCase)
            .filter(
                or_(
                    BugCase.title.ilike(pattern),
                    BugCase.root_cause.ilike(pattern),
                    BugCase.solution.ilike(pattern),
                )
            )
            .limit(limit)
            .all()
        )
        return [
            {"id": b.id, "title": b.title, "category": b.category, "severity": b.severity}
            for b in items
        ]

    def search_chats():
        items = (
            db.query(ChatSession)
            .filter(ChatSession.title.ilike(pattern))
            .limit(limit)
            .all()
        )
        return [
            {"id": c.id, "title": c.title, "model": c.model}
            for c in items
        ]

    search_map = {
        "logs": search_logs,
        "knowledge": search_knowledge,
        "analyses": search_analyses,
        "reports": search_reports,
        "bugs": search_bugs,
        "chats": search_chats,
    }

    if type == "all":
        for key, fn in search_map.items():
            try:
                result[key] = fn()
            except Exception:
                result[key] = []
    elif type in search_map:
        try:
            result[type] = search_map[type]()
        except Exception:
            result[type] = []
    else:
        return {"error": f"不支持的类型: {type}", "supported_types": list(search_map.keys())}

    result["total_hits"] = sum(len(v) for k, v in result.items() if k not in ("query", "type", "total_hits"))
    return result
