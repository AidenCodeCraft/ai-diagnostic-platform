"""对话截图识别编排：校验 → 存储 → OCR → 路由 →（必要时）视觉 → 落库。

同步执行（2~5 秒），失败不阻断提问：记录 status=failed 与原因，
由证据块标注"截图识别失败"，用户仍可继续描述问题。
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models import ChatImageUpload
from app.services.diagnostics.log_storage import LogStorage
from app.services.providers.vision import (
    DeepSeekVisionProvider,
    VisionProviderError,
    load_vision_prompt,
)
from app.services.vision.routing import PATH_OCR, PATH_OCR_VISION, PATH_VISION, decide_path

logger = get_logger(__name__)

MAX_BYTES = 32 * 1024 * 1024  # 文档：base64/URL 单图上限 32MiB
MAX_TEXT_FOR_CONTEXT = 6000

# 只按文件头判断类型：扩展名可伪造，直接把 .exe 改名 .png 会送去解码失败
_PNG_MAGIC = bytes([0x89]) + b"PNG" + bytes([0x0D, 0x0A, 0x1A, 0x0A])
_JPEG_MAGIC = bytes([0xFF, 0xD8, 0xFF])
_TIFF_LE = bytes([0x49, 0x49, 0x2A, 0x00])
_TIFF_BE = bytes([0x4D, 0x4D, 0x00, 0x2A])
_MAGIC = (
    (_PNG_MAGIC, "image/png", ".png"),
    (_JPEG_MAGIC, "image/jpeg", ".jpg"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
    (b"BM", "image/bmp", ".bmp"),
    (_TIFF_LE, "image/tiff", ".tiff"),
    (_TIFF_BE, "image/tiff", ".tiff"),
)
# WebP 也以 RIFF 开头，必须再看第 8~12 字节，否则 WAV/AVI 会被当成图片
_WEBP_PREFIX = (b"RIFF", b"WEBP")


class ChatImageError(ValueError):
    """上传校验失败（类型/大小）。"""


def sniff_mime(data: bytes) -> Optional[str]:
    """按文件头判断类型（文档：格式由内容判断，不看扩展名/MIME 声明）。"""
    if len(data) >= 12 and data[:4] == _WEBP_PREFIX[0] and data[8:12] == _WEBP_PREFIX[1]:
        return "image/webp"
    for magic, mime, _ext in _MAGIC:
        if data.startswith(magic):
            return mime
    return None


def _extension_for(mime: str) -> str:
    for _magic, known, ext in _MAGIC:
        if known == mime:
            return ext
    return ".bin"


class ChatImageService:
    def __init__(
        self,
        db: Session,
        provider: Optional[DeepSeekVisionProvider] = None,
        storage: Optional[LogStorage] = None,
    ):
        self.db = db
        self.provider = provider or DeepSeekVisionProvider()
        self.storage = storage or LogStorage()

    # ------------------------------------------------------------------
    # 上传与识别
    # ------------------------------------------------------------------

    def upload(
        self,
        data: bytes,
        filename: Optional[str] = None,
        session_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> ChatImageUpload:
        if not data:
            raise ChatImageError("文件为空")
        if len(data) > MAX_BYTES:
            raise ChatImageError(f"图片超过 {MAX_BYTES // (1024 * 1024)}MB 上限")

        mime = sniff_mime(data)
        if mime is None:
            raise ChatImageError("只支持 PNG / JPEG / WebP 图片")

        digest = hashlib.sha256(data).hexdigest()
        record = ChatImageUpload(
            session_id=session_id,
            user_id=user_id,
            filename=(filename or f"screenshot{_extension_for(mime)}")[:255],
            mime=mime,
            size_bytes=len(data),
            sha256=digest,
            status="recognizing",
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)

        record.storage_ref = self._store(data, mime)
        self._recognize(record, data, mime)
        self.db.commit()
        self.db.refresh(record)
        return record

    def _store(self, data: bytes, mime: str) -> Optional[str]:
        try:
            suffix = _extension_for(mime)
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                handle.write(data)
                temp_path = Path(handle.name)
            reference = self.storage.save(temp_path, f"screenshot{suffix}", project_id=0)
            temp_path.unlink(missing_ok=True)
            return reference
        except Exception as exc:  # noqa: BLE001 - 存储失败不影响识别
            logger.warning("[chat-image] 存储截图失败: %s", exc)
            return None

    def _recognize(self, record: ChatImageUpload, data: bytes, mime: str) -> None:
        # 同一张图重复上传：直接复用语料，避免重复计费（设计 §4 去重）
        cached = (
            self.db.query(ChatImageUpload)
            .filter(
                ChatImageUpload.sha256 == record.sha256,
                ChatImageUpload.id != record.id,
                ChatImageUpload.status == "succeeded",
                ChatImageUpload.extracted_text.isnot(None),
            )
            .first()
        )
        if cached is not None:
            record.status = "succeeded"
            record.recognize_path = cached.recognize_path
            record.extracted_text = cached.extracted_text
            record.usage = {"reused_from": cached.id}
            logger.info("[chat-image] 复用已有识别结果 id=%s (sha256=%s)", cached.id, record.sha256[:12])
            return

        ocr_text = ""
        ocr_error: Optional[str] = None
        try:
            ocr_result = self.provider.ocr(data, record.filename or "image.png")
            ocr_text = str(ocr_result.get("text") or "")
            record.usage = {"ocr_pages": ocr_result.get("pages", 0), **(ocr_result.get("usage") or {})}
            truncated = ocr_result.get("truncated_pages") or []
            if truncated:
                # finish_reason=length：该页文本不完整，不能当成识别成功
                record.usage["ocr_truncated_pages"] = truncated
                logger.warning("[ChatImage] OCR 输出被截断，页: %s", truncated)
        except VisionProviderError as exc:
            ocr_error = str(exc)
            logger.warning("[chat-image] OCR 失败 id=%s: %s", record.id, exc)

        path = decide_path(ocr_text, ocr_failed=bool(ocr_error))
        final_text = ocr_text

        if path == PATH_VISION:
            try:
                prompt = load_vision_prompt()
                vision_result = self.provider.describe(data, mime, prompt)
                vision_text = str(vision_result.get("text") or "")
                record.usage = {**(record.usage or {}), "vision_usage": vision_result.get("usage") or {}}
                if ocr_text:
                    path = PATH_OCR_VISION
                    final_text = f"{ocr_text}\n\n[视觉补充]\n{vision_text}".strip()
                else:
                    final_text = vision_text
            except (VisionProviderError, Exception) as exc:  # noqa: BLE001
                logger.warning("[chat-image] 视觉兜底失败 id=%s: %s", record.id, exc)
                if not final_text:
                    record.status = "failed"
                    record.error_message = (ocr_error or str(exc))[:500]
                    record.recognize_path = PATH_VISION
                    return
                path = PATH_OCR

        if not final_text.strip():
            record.status = "failed"
            record.error_message = "未识别到可用文字"
            record.recognize_path = path
            return

        record.status = "succeeded"
        record.recognize_path = path
        record.extracted_text = final_text[:20000]
        logger.info(
            "[chat-image] 识别完成 id=%s path=%s chars=%d", record.id, path, len(final_text),
        )

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def bind_to_session(
        self, image_ids: List[int], session_id: int, user_id: Optional[int] = None,
    ) -> int:
        """把前端上传的截图绑定到当前会话（发送消息时调用）。

        为什么不在上传时就绑定：用户可能先粘图、再新建会话提问；
        以上传时的 session_id 为准会导致证据丢失。发送时绑定是唯一可靠时机。
        """
        if not image_ids:
            return 0
        query = self.db.query(ChatImageUpload).filter(ChatImageUpload.id.in_(image_ids))
        if user_id is not None:
            query = query.filter(ChatImageUpload.user_id == user_id)
        bound = 0
        for record in query.all():
            record.session_id = session_id
            bound += 1
        if bound:
            self.db.commit()
        return bound

    def get(self, image_id: int) -> Optional[ChatImageUpload]:
        return self.db.query(ChatImageUpload).filter(ChatImageUpload.id == image_id).first()

    def get_many(self, image_ids: List[int]) -> List[ChatImageUpload]:
        if not image_ids:
            return []
        rows = (
            self.db.query(ChatImageUpload)
            .filter(ChatImageUpload.id.in_(image_ids))
            .all()
        )
        order = {value: index for index, value in enumerate(image_ids)}
        return sorted(rows, key=lambda row: order.get(row.id, len(order)))

    def texts_for_session(self, session_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """会话最近截图的可用于诊断的文本（证据块用）。"""
        rows = (
            self.db.query(ChatImageUpload)
            .filter(
                ChatImageUpload.session_id == session_id,
                ChatImageUpload.status == "succeeded",
                ChatImageUpload.extracted_text.isnot(None),
            )
            .order_by(ChatImageUpload.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "image_id": row.id,
                "path": row.recognize_path or PATH_OCR,
                "text": (row.extracted_text or "")[:MAX_TEXT_FOR_CONTEXT],
            }
            for row in reversed(rows)
        ]
