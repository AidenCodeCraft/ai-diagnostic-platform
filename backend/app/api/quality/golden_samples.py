"""黄金集标注与审核 API。

权限：登录用户即可提交标注；「谁能审」由提交人角色决定（见 review_policy），
服务层已校验，路由不再重复判断角色。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_session
from app.models import User
from app.services.quality import GoldenSampleError, GoldenSampleService
from app.services.quality.review_policy import next_reviewer

router = APIRouter(prefix="/quality/golden-samples", tags=["quality"])


def _serialize(sample) -> Dict[str, Any]:
    return {
        "id": sample.id,
        "question": sample.question,
        "slots": sample.slots,
        "kb_expected": sample.kb_expected,
        "log_expected": sample.log_expected,
        "expected_conclusion": sample.expected_conclusion,
        "category": sample.category,
        "device_model": sample.device_model,
        "status": sample.status,
        "sample_version": sample.sample_version,
        "review_chain": sample.review_chain or [],
        "review_step": sample.review_step or 0,
        "next_reviewer": next_reviewer(sample.review_chain, sample.review_step or 0),
        "submitted_by": sample.submitted_by,
        "submitted_at": sample.submitted_at,
        "approved_by": sample.approved_by,
        "approved_at": sample.approved_at,
        "trace_id": sample.trace_id,
        "replay_snapshot_ref": sample.replay_snapshot_ref,
        "note": sample.note,
        "created_at": sample.created_at,
        "updated_at": sample.updated_at,
    }


def _handle(exc: GoldenSampleError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("", status_code=201)
def create_sample(
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    service = GoldenSampleService(db)
    try:
        sample = service.create(
            question=body.get("question", ""),
            actor_id=user.id,
            actor_role=user.role,
            actor_name=user.username,
            slots=body.get("slots"),
            kb_expected=body.get("kb_expected"),
            log_expected=body.get("log_expected"),
            expected_conclusion=body.get("expected_conclusion", "answered"),
            category=body.get("category"),
            device_model=body.get("device_model"),
            note=body.get("note"),
            replay_snapshot_ref=body.get("replay_snapshot_ref"),
            trace_id=body.get("trace_id"),
            submit=bool(body.get("submit", True)),
        )
    except GoldenSampleError as exc:
        raise _handle(exc) from exc
    return _serialize(sample)


@router.get("")
def list_samples(
    status: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    device_model: Optional[str] = Query(default=None),
    mine: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    result = GoldenSampleService(db).list(
        status=status, category=category, device_model=device_model,
        submitted_by=user.id if mine else None,
        page=page, page_size=page_size,
    )
    return {
        "items": [_serialize(s) for s in result["items"]],
        "total": result["total"], "page": page, "page_size": page_size,
    }


@router.get("/pending")
def pending_for_me(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    result = GoldenSampleService(db).pending_for(user.role, page=page, page_size=page_size)
    return {
        "items": [_serialize(s) for s in result["items"]],
        "total": result["total"], "page": page, "page_size": page_size,
    }


@router.get("/export")
def export_approved(
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    if user.role not in ("admin", "developer", "engineer"):
        raise HTTPException(status_code=403, detail="无权导出黄金集")
    rows = GoldenSampleService(db).export_approved()
    return {"total": len(rows), "items": rows}


@router.get("/{sample_id}")
def get_sample(
    sample_id: int,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),  # noqa: ARG001 — 仅校验登录
) -> Dict[str, Any]:
    try:
        return _serialize(GoldenSampleService(db).get(sample_id))
    except GoldenSampleError as exc:
        raise _handle(exc) from exc


@router.get("/{sample_id}/reviews")
def list_reviews(
    sample_id: int,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),  # noqa: ARG001
) -> Dict[str, Any]:
    from app.models import SampleReview

    service = GoldenSampleService(db)
    try:
        sample = service.get(sample_id)
    except GoldenSampleError as exc:
        raise _handle(exc) from exc
    rows = (
        db.query(SampleReview)
        .filter(SampleReview.sample_id == sample.id)
        .order_by(SampleReview.id.asc())
        .all()
    )
    return {
        "items": [
            {
                "id": r.id, "sample_version": r.sample_version,
                "actor_id": r.actor_id, "actor_name": r.actor_name,
                "role": r.role, "action": r.action, "reason": r.reason,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    }


@router.put("/{sample_id}")
def update_sample(
    sample_id: int,
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        sample = GoldenSampleService(db).update(
            sample_id,
            actor_id=user.id, actor_role=user.role, actor_name=user.username,
            **{k: v for k, v in body.items() if v is not None},
        )
    except GoldenSampleError as exc:
        raise _handle(exc) from exc
    return _serialize(sample)


@router.post("/{sample_id}/submit")
def submit_sample(
    sample_id: int,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        sample = GoldenSampleService(db).submit_sample(
            sample_id, actor_id=user.id, actor_role=user.role, actor_name=user.username,
        )
    except GoldenSampleError as exc:
        raise _handle(exc) from exc
    return _serialize(sample)


@router.post("/{sample_id}/review")
def review_sample(
    sample_id: int,
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    if "approve" not in body:
        raise HTTPException(status_code=400, detail="缺少 approve 字段")
    try:
        sample = GoldenSampleService(db).review(
            sample_id,
            actor_id=user.id, actor_role=user.role, actor_name=user.username,
            approve=bool(body["approve"]), reason=body.get("reason"),
        )
    except GoldenSampleError as exc:
        raise _handle(exc) from exc
    return _serialize(sample)


@router.post("/{sample_id}/supersede")
def supersede_sample(
    sample_id: int,
    body: Optional[Dict[str, Any]] = None,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        sample = GoldenSampleService(db).supersede(
            sample_id,
            actor_id=user.id, actor_role=user.role, actor_name=user.username,
            reason=(body or {}).get("reason"),
        )
    except GoldenSampleError as exc:
        raise _handle(exc) from exc
    return _serialize(sample)
