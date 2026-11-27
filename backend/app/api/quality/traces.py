"""检索轨迹查询 API —— 供「标注为回归样本」预填与失败复盘。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_session
from app.models import RetrievalTrace, User

router = APIRouter(prefix="/quality/traces", tags=["quality"])


def _serialize(trace: RetrievalTrace) -> Dict[str, Any]:
    return {
        "id": trace.id,
        "session_id": trace.session_id,
        "message_id": trace.message_id,
        "log_id": trace.log_id,
        "question": trace.question,
        "kb_candidates": trace.kb_candidates,
        "log_patterns": trace.log_patterns,
        "log_blocks": trace.log_blocks,
        "timings": trace.timings,
        "conclusion": trace.conclusion,
        "pipeline_version": trace.pipeline_version,
        "created_at": trace.created_at,
    }


@router.get("")
def list_traces(
    session_id: Optional[int] = Query(default=None),
    question: Optional[str] = Query(default=None, description="按问题文本精确过滤"),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),  # noqa: ARG001 — 仅校验登录
) -> Dict[str, Any]:
    query = db.query(RetrievalTrace)
    if session_id is not None:
        query = query.filter(RetrievalTrace.session_id == session_id)
    if question:
        query = query.filter(RetrievalTrace.question == question)
    rows = query.order_by(RetrievalTrace.id.desc()).limit(limit).all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}


@router.get("/{trace_id}")
def get_trace(
    trace_id: int,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),  # noqa: ARG001
) -> Dict[str, Any]:
    trace = db.query(RetrievalTrace).filter(RetrievalTrace.id == trace_id).first()
    if not trace:
        raise HTTPException(status_code=404, detail="轨迹不存在")
    return _serialize(trace)
