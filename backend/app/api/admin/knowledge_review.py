"""Admin knowledge review API — 自进化候选审核队列。"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.services.knowledge.profile_service import KnowledgeProfileService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/admin/knowledge/profiles", tags=["admin"])


@router.get("/drafts")
def list_drafts(db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """列出待审核的自进化候选（draft）。"""
    return {"items": KnowledgeProfileService(db).list_drafts_with_docs()}


@router.post("/{profile_id}/approve")
def approve(profile_id: int, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """审核通过：候选转为正式知识条目并进入检索。"""
    try:
        profile = KnowledgeProfileService(db).approve(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return KnowledgeProfileService.to_dict(profile)


@router.post("/{profile_id}/reject")
def reject(profile_id: int, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """审核驳回：删除候选及其草稿知识条目。"""
    try:
        KnowledgeProfileService(db).reject(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}
