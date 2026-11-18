"""管理后台操作审计：记录与查询。

约定：detail 中禁止写入密码、API Key 等敏感信息。
审计写入失败不得影响业务主流程（仅记录日志）。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models import User
from app.models.system.admin_audit import AdminAuditLog

logger = get_logger(__name__)


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def record_operation(
    db: Session,
    operator: Optional[User],
    action: str,
    *,
    target_type: Optional[str] = None,
    target_id: Any = None,
    detail: Optional[Dict[str, Any]] = None,
    result: str = "success",
    request: Optional[Request] = None,
) -> None:
    """写入一条管理后台操作记录；异常不外抛。"""
    try:
        db.add(AdminAuditLog(
            operator_id=getattr(operator, "id", None),
            operator_name=getattr(operator, "username", None),
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            detail=json.dumps(detail or {}, ensure_ascii=False),
            result=result,
            ip=_client_ip(request),
        ))
        db.commit()
    except Exception as exc:  # noqa: BLE001 - 审计失败不阻断主流程
        logger.warning("Failed to record admin operation %s: %s", action, exc)
        db.rollback()


def list_operations(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    action: Optional[str] = None,
    operator: Optional[str] = None,
    result: Optional[str] = None,
) -> Dict[str, Any]:
    """分页查询操作记录（按时间倒序）。"""
    query = db.query(AdminAuditLog)
    if action:
        query = query.filter(AdminAuditLog.action == action)
    if operator:
        query = query.filter(AdminAuditLog.operator_name.ilike(f"%{operator}%"))
    if result:
        query = query.filter(AdminAuditLog.result == result)

    total = query.count()
    rows = (
        query.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "operator_id": row.operator_id,
                "operator_name": row.operator_name,
                "action": row.action,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "detail": row.detail,
                "result": row.result,
                "ip": row.ip,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
