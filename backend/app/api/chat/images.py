"""对话截图上传与识别（Chat-Image-Recognition-Design I1/I2）。

同步识别：前端上传后立即拿到识别文本，用户能在提问前确认"识别到了什么"。
识别失败返回 200 + status=failed（不阻断提问，前端提示并允许重试）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_auth
from app.models import ChatImageUpload
from app.services.vision.image_service import ChatImageError, ChatImageService

router = APIRouter(prefix="/chat/images", tags=["chat"])

PREVIEW_CHARS = 300


def _serialize(record: ChatImageUpload) -> Dict[str, Any]:
    text = record.extracted_text or ""
    return {
        "id": record.id,
        "filename": record.filename,
        "status": record.status,
        "recognize_path": record.recognize_path,
        "text": text,
        "text_preview": text[:PREVIEW_CHARS],
        "error_message": record.error_message,
        "size_bytes": record.size_bytes,
        "storage_ref": record.storage_ref,
    }


@router.post("")
async def upload_image(
    file: UploadFile = File(...),
    session_id: Optional[int] = Form(None),
    db: Session = Depends(get_db_session),
    user_id: int = Depends(require_auth),
) -> Dict[str, Any]:
    """上传截图并识别（PNG / JPEG / WebP，≤20MB）。"""
    data = await file.read()
    try:
        record = ChatImageService(db).upload(
            data, filename=file.filename, session_id=session_id, user_id=user_id,
        )
    except ChatImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize(record)


@router.get("/{image_id}")
def get_image(
    image_id: int,
    db: Session = Depends(get_db_session),
    _user_id: int = Depends(require_auth),
) -> Dict[str, Any]:
    """查询截图识别结果。"""
    record = ChatImageService(db).get(image_id)
    if record is None:
        raise HTTPException(status_code=404, detail="截图不存在")
    return _serialize(record)
