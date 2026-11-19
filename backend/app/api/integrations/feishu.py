"""飞书回调入口（S1）。

安全模型：
  - 飞书无法携带我们的 JWT，因此本端点不走 require_auth，改为校验飞书自身的凭据；
  - 配置了 Encrypt Key → 必须验签 + 解密，否则 403；
  - 未配置 Encrypt Key → 必须校验 Verification Token，否则拒绝；
  - 两者都没配 → 直接 503，**不开放无校验的回调**（那等于允许任何人伪造事件）。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_auth
from app.core.config import settings
from app.core.logging_config import get_logger
from app.services.integrations.feishu.event_service import FeishuEventService
from app.services.integrations.feishu.security import (
    FeishuSecurityError,
    decrypt_payload,
    verify_signature,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/integrations/feishu", tags=["integrations"])


def _payload_dict(body: bytes) -> Dict[str, Any]:
    try:
        value = json.loads(body or b"{}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"请求体不是合法 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")
    return value


def _resolve_payload(request: Request, body: bytes) -> Dict[str, Any]:
    data = _payload_dict(body)
    encrypt_key = str(getattr(settings, "FEISHU_ENCRYPT_KEY", "") or "")
    verification_token = str(getattr(settings, "FEISHU_VERIFICATION_TOKEN", "") or "")

    if not encrypt_key and not verification_token:
        raise HTTPException(
            status_code=503,
            detail="飞书回调未配置校验凭据（FEISHU_ENCRYPT_KEY 或 FEISHU_VERIFICATION_TOKEN）",
        )

    if "encrypt" in data:
        if not encrypt_key:
            raise HTTPException(status_code=503, detail="收到加密事件但未配置 FEISHU_ENCRYPT_KEY")

        timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
        nonce = request.headers.get("X-Lark-Request-Nonce", "")
        signature = request.headers.get("X-Lark-Signature", "")
        if signature and not verify_signature(timestamp, nonce, encrypt_key, body, signature):
            logger.warning("[feishu] signature mismatch (ts=%s nonce=%s)", timestamp, nonce)
            raise HTTPException(status_code=403, detail="签名校验失败")

        try:
            return decrypt_payload(encrypt_key, str(data["encrypt"]))
        except FeishuSecurityError as exc:
            logger.warning("[feishu] decrypt failed: %s", exc)
            raise HTTPException(status_code=400, detail=f"事件解密失败: {exc}") from exc

    token = str(data.get("token") or (data.get("header") or {}).get("token") or "")
    if verification_token and token != verification_token:
        logger.warning("[feishu] verification token mismatch")
        raise HTTPException(status_code=403, detail="Verification Token 校验失败")
    return data


@router.post("/events")
async def receive_event(request: Request, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """接收飞书事件（含 url_verification 握手）。"""
    if not bool(getattr(settings, "FEISHU_ENABLED", False)):
        raise HTTPException(status_code=404, detail="飞书集成未启用")

    body = await request.body()
    payload = _resolve_payload(request, body)

    # 事件订阅配置时的握手：必须原样回 challenge，否则飞书判定回调不可用
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    result = FeishuEventService(db).handle(payload)
    return {"code": 0, **result}


@router.get("/attachments/{attachment_id}")
def get_attachment(
    attachment_id: int,
    db: Session = Depends(get_db_session),
    _user=Depends(require_auth),
) -> Dict[str, Any]:
    """查询图片识别状态与结果。"""
    from app.services.integrations.feishu.event_service import FeishuEventService as _Svc

    attachment = _Svc(db).get_attachment(attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="附件不存在")

    return {
        "id": attachment.id,
        "message_id": attachment.message_id,
        "image_key": attachment.image_key,
        "status": attachment.status,
        "recognize_path": attachment.recognize_path,
        "extracted_text": attachment.extracted_text,
        "usage": attachment.usage,
        "error_message": attachment.error_message,
        "storage_ref": attachment.storage_ref,
        "created_at": attachment.created_at.isoformat() if attachment.created_at else None,
    }
