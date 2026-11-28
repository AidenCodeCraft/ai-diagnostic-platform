"""分片上传（大文件断点续传）。

浏览器把文件切成固定大小的块，先 init 拿到 upload_id，再逐块 PUT，
最后 complete 由服务端拼装成一个完整文件并复用 LogService 入库。

设计目标：
- 单块失败只重传该块，不必重传整个 100MB 日志；
- 同一个 (fingerprint, request_id) 重新 init 时返回已收到的块，实现断点续传；
- 拼装后的文件仍走既有上传校验（大小/二进制/压缩包解包/去重存储）。
"""

from __future__ import annotations

import json
import math
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import get_logger
from app.models import Log
from app.services.diagnostics.log_service import LogService, LogUploadError

logger = get_logger(__name__)

CHUNK_SIZE = 8 * 1024 * 1024
_UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class ChunkedUploadError(LogUploadError):
    """分片上传错误（带 HTTP 状态码）。"""


class ChunkedUploadService:
    def __init__(self, db: Session):
        self.db = db

    # -- paths ---------------------------------------------------------
    def _root(self) -> Path:
        root = Path(settings.UPLOAD_DIR) / ".chunks"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _dir(self, upload_id: str) -> Path:
        if not _UPLOAD_ID_RE.match(upload_id or ""):
            raise ChunkedUploadError("上传任务不存在", status_code=404)
        path = self._root() / upload_id
        if not path.is_dir():
            raise ChunkedUploadError("上传任务不存在或已过期", status_code=404)
        return path

    @staticmethod
    def _read_meta(path: Path) -> Dict[str, Any]:
        meta_path = path / "meta.json"
        if not meta_path.exists():
            raise ChunkedUploadError("上传任务元数据缺失", status_code=404)
        return json.loads(meta_path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_meta(path: Path, meta: Dict[str, Any]) -> None:
        (path / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8",
        )

    @staticmethod
    def _received(path: Path) -> List[int]:
        return sorted(
            int(p.stem) for p in path.glob("*.part") if p.stem.isdigit()
        )

    def _payload(self, path: Path, meta: Dict[str, Any]) -> Dict[str, Any]:
        received = self._received(path)
        return {
            "upload_id": path.name,
            "filename": meta.get("filename"),
            "size": meta.get("size"),
            "chunk_size": CHUNK_SIZE,
            "total_chunks": meta.get("total_chunks"),
            "received": received,
            "received_count": len(received),
        }

    # -- API -----------------------------------------------------------
    def init(
        self,
        filename: str,
        size: int,
        *,
        project_id: Optional[int] = None,
        upload_user_id: Optional[int] = None,
        description: Optional[str] = None,
        fingerprint: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        safe_name = Path(filename or "upload.log").name
        max_bytes = max(1, int(settings.MAX_UPLOAD_MB)) * 1024 * 1024
        if size <= 0:
            raise ChunkedUploadError("文件为空", status_code=400)
        if size > max_bytes:
            raise ChunkedUploadError(
                f"文件超过上传大小限制（{settings.MAX_UPLOAD_MB}MB）",
                status_code=413,
            )

        # 断点续传：同一指纹且仍在接收中的任务直接复用
        if fingerprint:
            for candidate in self._root().iterdir():
                if not candidate.is_dir() or not _UPLOAD_ID_RE.match(candidate.name):
                    continue
                try:
                    meta = self._read_meta(candidate)
                except ChunkedUploadError:
                    continue
                if (
                    meta.get("fingerprint") == fingerprint
                    and int(meta.get("size") or 0) == int(size)
                    and not meta.get("completed")
                ):
                    return self._payload(candidate, meta)

        upload_id = uuid.uuid4().hex
        path = self._root() / upload_id
        path.mkdir(parents=True, exist_ok=False)
        meta = {
            "filename": safe_name,
            "size": int(size),
            "chunk_size": CHUNK_SIZE,
            "total_chunks": max(1, math.ceil(size / CHUNK_SIZE)),
            "project_id": project_id,
            "upload_user_id": upload_user_id,
            "description": description,
            "fingerprint": fingerprint,
            "request_id": request_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_meta(path, meta)
        logger.info(
            "[upload] chunked init upload_id=%s size=%s chunks=%s fingerprint=%s",
            upload_id, size, meta["total_chunks"], fingerprint,
        )
        return self._payload(path, meta)

    def status(self, upload_id: str) -> Dict[str, Any]:
        path = self._dir(upload_id)
        return self._payload(path, self._read_meta(path))

    def save_chunk(self, upload_id: str, index: int, data: bytes) -> Dict[str, Any]:
        path = self._dir(upload_id)
        meta = self._read_meta(path)
        total = int(meta.get("total_chunks") or 0)
        if index < 0 or index >= total:
            raise ChunkedUploadError("分片序号越界", status_code=400)
        if not data:
            raise ChunkedUploadError("分片内容为空", status_code=400)
        if len(data) > CHUNK_SIZE + 1024:
            raise ChunkedUploadError("分片过大", status_code=413)
        (path / f"{index:08d}.part").write_bytes(data)
        payload = self._payload(path, meta)
        logger.debug(
            "[upload] chunk upload_id=%s index=%s received=%s/%s",
            upload_id, index, payload["received_count"], total,
        )
        return payload

    def complete(self, upload_id: str) -> Log:
        path = self._dir(upload_id)
        meta = self._read_meta(path)
        total = int(meta.get("total_chunks") or 0)
        received = self._received(path)
        if len(received) != total:
            missing = [i for i in range(total) if i not in set(received)]
            raise ChunkedUploadError(
                f"分片不完整，缺少 {len(missing)} 块", status_code=400,
            )

        assembled = path / "assembled.log"
        try:
            with assembled.open("wb") as out:
                for index in range(total):
                    with (path / f"{index:08d}.part").open("rb") as part:
                        shutil.copyfileobj(part, out, length=1024 * 1024)
            with assembled.open("rb") as handle:
                upload = UploadFile(file=handle, filename=str(meta.get("filename") or "upload.log"))
                log = LogService(self.db).upload_log(
                    file=upload,
                    project_id=meta.get("project_id"),
                    upload_user_id=meta.get("upload_user_id"),
                    description=meta.get("description"),
                )
            meta["completed"] = True
            self._write_meta(path, meta)
            logger.info(
                "[upload] chunked complete upload_id=%s log_id=%s size=%s",
                upload_id, getattr(log, "id", None), meta.get("size"),
            )
            return log
        finally:
            shutil.rmtree(path, ignore_errors=True)
