"""Admin dashboard API — aggregated statistics and system config."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.models import User, Project, Log, Analysis, KnowledgeDocument


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/admin", tags=["admin"])

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "raw", "system_config.json")


def _load_config() -> Dict[str, Any]:
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_config(config: Dict[str, Any]):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


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

    completed = db.query(func.count(Analysis.id)).filter(Analysis.status == "completed").scalar() or 0
    failed = db.query(func.count(Analysis.id)).filter(Analysis.status == "failed").scalar() or 0

    seven_days_ago = now - timedelta(days=7)
    recent = (
        db.query(func.date(Analysis.created_at), func.count(Analysis.id))
        .filter(Analysis.created_at >= seven_days_ago)
        .group_by(func.date(Analysis.created_at))
        .order_by(func.date(Analysis.created_at))
        .all()
    )
    analysis_trend = [{"date": str(d), "count": c} for d, c in recent]

    total_log_size = db.query(func.sum(Log.size)).scalar() or 0

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
        "active_plugins": 0,
    }


@router.get("/config/llm")
def get_llm_config():
    """Get saved LLM configuration (merged with environment variables)."""
    import os
    config = _load_config()
    llm = config.get("llm", {
        "provider": "deepseek",
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    })
    # 环境变量优先级高于文件配置（Docker Compose 直接注入）
    env_key = os.getenv("DEEPSEEK_API_KEY", "")
    if env_key:
        llm["api_key"] = env_key
    return llm


@router.put("/config/llm")
def save_llm_config(body: Dict[str, Any]):
    """Save LLM configuration."""
    config = _load_config()
    config["llm"] = {
        "provider": body.get("provider", "deepseek"),
        "api_key": body.get("api_key", ""),
        "base_url": body.get("base_url", "https://api.deepseek.com"),
        "model": body.get("model", "deepseek-chat"),
    }
    _save_config(config)
    return {"ok": True, "message": "LLM 配置已保存"}
