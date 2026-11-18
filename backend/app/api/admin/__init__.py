"""Admin dashboard API — aggregated statistics and system config."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_admin_user, require_auth
from app.database import session as session_module
from app.models import User, Project, Log, Analysis, KnowledgeDocument
from app.services.system.audit_log import record_operation


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


def _mask_api_key(key: str) -> str:
    """脱敏 API Key：仅保留前 3 位与后 4 位。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:3]}****{key[-4:]}"


def _is_masked(key: str) -> bool:
    """判断传入值是否为脱敏占位（含 ****）。"""
    return "****" in (key or "")


def _find_existing_key(old_models: list, index: int, model_name: Any) -> str:
    """按索引优先、模型标识兜底，取回已保存的明文 key。"""
    if index < len(old_models):
        key = str(old_models[index].get("api_key") or "")
        if key:
            return key
    for old in old_models:
        if old.get("model") == model_name:
            key = str(old.get("api_key") or "")
            if key:
                return key
    return ""


@router.get("/stats", dependencies=[Depends(require_admin)])
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

    from app.services.system.concurrency import chat_gate

    return {
        "active_chat_streams": chat_gate.inflight,
        "total_users": total_users,
        "total_projects": total_projects,
        "total_logs": total_logs,
        "total_analyses": total_analyses,
        "total_knowledge": total_knowledge,
        "analysis_completed": completed,
        "analysis_failed": failed,
        "analysis_trend": analysis_trend,
        "total_log_size_bytes": total_log_size,
    }


@router.get("/audit-logs", dependencies=[Depends(require_admin)])
def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action: Optional[str] = Query(default=None),
    operator: Optional[str] = Query(default=None),
    result: Optional[str] = Query(default=None),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """管理后台操作审计记录（按时间倒序）。"""
    from app.services.system.audit_log import list_operations

    return list_operations(
        db, page=page, page_size=page_size,
        action=action, operator=operator, result=result,
    )


@router.get("/config/llm", dependencies=[Depends(require_admin)])
def get_llm_config():
    """Get saved LLM configuration (supports multiple models).

    api_key 一律脱敏返回，避免通过接口泄露明文密钥。
    """
    import os
    config = _load_config()
    
    # 新格式：支持多模型配置
    if "llm" in config and "models" in config["llm"]:
        models = [dict(m) for m in config["llm"]["models"]]
        # 环境变量优先级高于文件配置
        env_key = os.getenv("DEEPSEEK_API_KEY", "")
        if env_key:
            for model in models:
                if model.get("provider") == "deepseek" and not model.get("api_key"):
                    model["api_key"] = env_key
        for model in models:
            model["api_key"] = _mask_api_key(str(model.get("api_key") or ""))
        return {"models": models}
    
    # 兼容旧格式或提供默认配置
    default_model = {
        "name": "DeepSeek V4 Flash",
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "api_key": _mask_api_key(os.getenv("DEEPSEEK_API_KEY", "")),
        "base_url": "https://api.deepseek.com",
        "temperature": 1.0,
        "max_tokens": 8000,
        "isDefault": True
    }
    
    return {"models": [default_model]}


@router.put("/config/llm", dependencies=[Depends(require_admin)])
def save_llm_config(
    body: Dict[str, Any],
    request: Request,
    db: Session = Depends(get_db_session),
    operator: User = Depends(require_admin_user),
):
    """Save LLM configuration (supports multiple models).

    收到空值或脱敏占位（含 ****）时沿用已保存的 key，避免把掩码写回配置。
    """
    config = _load_config()
    old_llm = config.get("llm") or {}
    old_models = old_llm.get("models") or []

    # 新格式：保存多模型配置
    if "models" in body:
        models = [dict(m) for m in body["models"]]
        for idx, model in enumerate(models):
            key = str(model.get("api_key") or "")
            if key and not _is_masked(key):
                continue
            model["api_key"] = _find_existing_key(old_models, idx, model.get("model"))
        config["llm"] = {"models": models}
    else:
        # 兼容旧格式（单模型）
        key = str(body.get("api_key") or "")
        if not key or _is_masked(key):
            key = str(old_llm.get("api_key") or "")
        config["llm"] = {
            "provider": body.get("provider", "deepseek"),
            "api_key": key,
            "base_url": body.get("base_url", "https://api.deepseek.com"),
            "model": body.get("model", "deepseek-v4-flash"),
        }
    
    _save_config(config)
    record_operation(
        db, operator, "config.llm.save",
        target_type="llm_config",
        detail={"models": [str(m.get("model") or "") for m in (config["llm"].get("models") or [])]},
        request=request,
    )
    return {"ok": True, "message": "LLM 配置已保存"}


@router.get("/config/llm/models", dependencies=[Depends(require_auth)])
def get_available_models():
    """Get list of configured models for selection in chat interface."""
    config = _load_config()
    
    if "llm" in config and "models" in config["llm"]:
        models = config["llm"]["models"]
        return {
            "models": [
                {
                    "label": m.get("name", m.get("model", "Unknown")),
                    "value": m.get("model"),
                    "isDefault": m.get("isDefault", False)
                }
                for m in models
            ]
        }
    
    # 默认返回
    return {
        "models": [
            {"label": "DeepSeek V4 Flash", "value": "deepseek-v4-flash", "isDefault": True},
            {"label": "DeepSeek V4 Pro", "value": "deepseek-v4-pro", "isDefault": False}
        ]
    }


@router.get("/config/system", dependencies=[Depends(require_auth)])
def get_system_config():
    """Get system parameters (snake_case keys)."""
    from app.services.system.system_config import get_system_config as load_system_config
    return load_system_config()


@router.put("/config/system", dependencies=[Depends(require_admin)])
def save_system_config(
    body: Dict[str, Any],
    request: Request,
    db: Session = Depends(get_db_session),
    operator: User = Depends(require_admin_user),
):
    """Save system parameters. Accepts snake_case keys (camelCase tolerated)."""
    from app.services.system.system_config import KEY_ALIASES, normalize

    config = _load_config()
    raw = dict(config.get("system") or {})
    for key, value in body.items():
        raw[KEY_ALIASES.get(key, key)] = value
    config["system"] = normalize(raw)
    _save_config(config)
    record_operation(
        db, operator, "config.system.save",
        target_type="system_config",
        detail={"keys": sorted(body.keys())},
        request=request,
    )
    return {"ok": True, "message": "系统参数已保存", "config": config["system"]}


@router.post("/knowledge/seed", dependencies=[Depends(require_admin)])
def seed_knowledge(
    request: Request,
    reset: bool = Query(default=False),
    db: Session = Depends(get_db_session),
    operator: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    """导入知识库示例数据（四类模板）；reset=true 时先删除同名示例再重建。"""
    from app.services.knowledge.seed_service import seed

    result = seed(db, reset=reset)
    record_operation(
        db, operator, "knowledge.seed",
        target_type="knowledge",
        detail={"reset": reset},
        request=request,
    )
    return result
