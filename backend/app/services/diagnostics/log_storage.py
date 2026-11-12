"""日志存储抽象 — 本地文件系统 / MinIO 对象存储。

MinIO 启用时，日志保存为 `minio://<bucket>/<key>` 引用；
解析/分析前通过 `materialize()` 下载到本地临时文件。
MinIO 未启用或客户端不可用时自动回退本地路径。
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class LogStorageError(RuntimeError):
    """日志存储读写失败。"""


class LogStorage:
    def __init__(self) -> None:
        self.enabled = bool(getattr(settings, "MINIO_ENABLED", False))
        self.bucket = str(getattr(settings, "MINIO_BUCKET", "diagnostic-logs") or "diagnostic-logs")
        self._client = self._create_client() if self.enabled else None

    # ------------------------------------------------------------------
    # Client
    # ------------------------------------------------------------------

    def _create_client(self) -> Optional[object]:
        try:
            from minio import Minio
        except ImportError:
            logger.warning("[LogStorage] minio package not installed; using local storage")
            return None
        try:
            return Minio(
                str(settings.MINIO_ENDPOINT),
                access_key=str(settings.MINIO_ACCESS_KEY),
                secret_key=str(settings.MINIO_SECRET_KEY),
                secure=bool(settings.MINIO_SECURE),
            )
        except Exception as exc:  # noqa: BLE001 - 回退本地存储
            logger.warning("[LogStorage] MinIO init failed: %s; using local storage", exc)
            return None

    @property
    def remote_available(self) -> bool:
        return self.enabled and self._client is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, local_path: str | Path, filename: str) -> str:
        """保存日志；返回存储引用（minio://... 或本地绝对路径）。"""
        path = Path(local_path)
        if not self.remote_available:
            return str(path)
        key = f"logs/{uuid.uuid4().hex}_{Path(filename).name}"
        try:
            self._client.fput_object(self.bucket, key, str(path))  # type: ignore[attr-defined]
            logger.info("[LogStorage] uploaded %s -> minio://%s/%s", filename, self.bucket, key)
            return f"minio://{self.bucket}/{key}"
        except Exception as exc:  # noqa: BLE001 - 回退本地存储
            logger.warning("[LogStorage] upload failed (%s); keeping local file", exc)
            return str(path)

    def materialize(self, reference: str) -> Path:
        """把存储引用解析为本地可读路径（MinIO 引用会下载到临时目录）。"""
        reference = str(reference or "")
        if not reference.startswith("minio://"):
            return Path(reference)

        if not self.remote_available:
            raise LogStorageError(
                "日志存储在 MinIO 中，但 MinIO 未启用或客户端不可用，无法读取"
            )

        bucket, _, key = reference[len("minio://"):].partition("/")
        if not bucket or not key:
            raise LogStorageError(f"无效的 MinIO 引用: {reference}")

        target = Path(tempfile.gettempdir()) / "diag_logs" / Path(key).name
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._client.fget_object(bucket, key, str(target))  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            raise LogStorageError(f"下载 MinIO 日志失败: {exc}") from exc
        return target

    def delete(self, reference: str) -> None:
        """删除日志（对象存储对象或本地文件）。"""
        reference = str(reference or "")
        if reference.startswith("minio://"):
            if not self.remote_available:
                return
            bucket, _, key = reference[len("minio://"):].partition("/")
            try:
                self._client.remove_object(bucket, key)  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001 - 删除失败不阻断
                logger.warning("[LogStorage] remove object failed: %s", exc)
            return

        path = Path(reference)
        if path.exists():
            path.unlink()
