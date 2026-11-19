"""日志存储抽象 — 本地文件系统 / MinIO 对象存储。

MinIO 启用时，日志保存为 `minio://<bucket>/<key>` 引用；
解析/分析前通过 `materialize()` 下载到本地临时文件。
MinIO 未启用或客户端不可用时自动回退本地路径。
"""

from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timedelta, timezone
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
        self.presign_ttl = int(getattr(settings, "MINIO_PRESIGN_TTL_SECONDS", 900) or 900)
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
            client = Minio(
                str(settings.MINIO_ENDPOINT),
                access_key=str(settings.MINIO_ACCESS_KEY),
                secret_key=str(settings.MINIO_SECRET_KEY),
                secure=bool(settings.MINIO_SECURE),
            )
        except Exception as exc:  # noqa: BLE001 - 回退本地存储
            logger.warning("[LogStorage] MinIO init failed: %s; using local storage", exc)
            return None

        # 首次部署时 bucket 可能尚不存在：这里确保其存在，避免首个上传静默回退本地。
        # 建桶失败（权限/网络）记录 warning 并回退本地存储（保持既有回退语义）。
        try:
            self._ensure_bucket(client)
        except Exception as exc:  # noqa: BLE001 - 回退本地存储
            logger.warning(
                "[LogStorage] cannot ensure bucket %r (%s); using local storage",
                self.bucket, exc,
            )
            return None
        return client

    def _ensure_bucket(self, client: object) -> None:
        """确保目标 bucket 存在（幂等；多 worker 并发首次启动安全）。

        - 不存在 → ``make_bucket`` 并记录 info 日志；
        - 并发场景下 ``make_bucket`` 可能抛“已存在”类错误（S3 code
          ``BucketAlreadyOwnedByYou`` / ``BucketAlreadyExists``），此时重新
          ``bucket_exists`` 确认后视为成功（幂等兜底）；
        - 其他错误（权限/网络等）继续抛出，由 `_create_client` 记录 warning 并回退本地。
        """
        bucket = self.bucket
        if client.bucket_exists(bucket):  # type: ignore[attr-defined]
            return

        try:
            client.make_bucket(bucket)  # type: ignore[attr-defined]
            logger.info("[LogStorage] created MinIO bucket %r", bucket)
        except Exception as exc:  # noqa: BLE001 - 需区分“并发已存在”与真实失败
            code = getattr(exc, "code", None)
            if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                if client.bucket_exists(bucket):  # type: ignore[attr-defined]
                    logger.info(
                        "[LogStorage] bucket %r already created concurrently; reusing", bucket
                    )
                    return
            raise

    @property
    def remote_available(self) -> bool:
        return self.enabled and self._client is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, local_path: str | Path, filename: str, project_id: Optional[int] = None) -> str:
        """保存日志；返回存储引用（minio://... 或本地绝对路径）。

        对象键按项目 + 日期分层（`logs/p{project_id}/{yyyymmdd}/{uuid}_{name}`）：
        这样按项目清理/迁移/统计成本可控，不必扫全桶。旧对象键（`logs/<uuid>_<name>`）
        仍然可读——引用里存的是完整键，读取路径不依赖布局规则。
        """
        path = Path(local_path)
        if not self.remote_available:
            return str(path)
        date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
        key = f"logs/p{int(project_id or 0)}/{date_part}/{uuid.uuid4().hex}_{Path(filename).name}"
        try:
            self._client.fput_object(self.bucket, key, str(path))  # type: ignore[attr-defined]
            logger.info("[LogStorage] uploaded %s -> minio://%s/%s", filename, self.bucket, key)
            return f"minio://{self.bucket}/{key}"
        except Exception as exc:  # noqa: BLE001 - 回退本地存储
            logger.warning("[LogStorage] upload failed (%s); keeping local file", exc)
            return str(path)

    def presigned_get(self, reference: str, ttl_seconds: Optional[int] = None) -> Optional[str]:
        """生成对象下载的预签名 URL（默认 15 分钟）。

        桶必须保持私有：对外只发短时预签名链接，不发公开 URL，
        否则日志里的设备序列号、网络配置会变成可被搜索引擎抓到的内容。
        """
        reference = str(reference or "")
        if not reference.startswith("minio://"):
            return None
        if not self.remote_available:
            return None

        bucket, _, key = reference[len("minio://"):].partition("/")
        if not bucket or not key:
            return None

        ttl = int(ttl_seconds or self.presign_ttl)
        try:
            return self._client.presigned_get_object(  # type: ignore[attr-defined]
                bucket, key, expires=timedelta(seconds=ttl),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LogStorage] presign failed for %s: %s", key, exc)
            return None

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
