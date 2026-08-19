"""Knowledge image storage — MinIO（生产）+ 本地文件系统（开发回退）。

两种后端共用同一接口：
  - save(storage_key, data, content_type)
  - get_bytes(storage_key)
  - presign_url(storage_key, expires)  仅 MinIO 支持，本地返回 None
  - delete(storage_key)

MinIO 客户端采用惰性导入，`MINIO_ENABLED=False` 时无需安装 minio 包即可运行本地模式。
"""

from __future__ import annotations

import io
from datetime import timedelta
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ImageStorageError(Exception):
    """图片存储层错误。"""


class KnowledgeImageStorage:
    """知识库图片对象存储抽象（MinIO / 本地）。"""

    def __init__(self) -> None:
        self._minio_client = None

    # ------------------------------------------------------------------
    # 模式与配置
    # ------------------------------------------------------------------

    @property
    def use_minio(self) -> bool:
        return bool(getattr(settings, "MINIO_ENABLED", False))

    @property
    def bucket(self) -> str:
        return str(getattr(settings, "MINIO_KNOWLEDGE_BUCKET", "knowledge-images"))

    def _get_minio(self):
        if self._minio_client is None:
            try:
                from minio import Minio
            except ImportError as exc:  # pragma: no cover - 仅在启用 MinIO 且未装依赖时触发
                raise ImageStorageError(
                    "MinIO 已启用但未安装 minio 客户端，请执行 `pip install minio`"
                ) from exc

            client = Minio(
                str(settings.MINIO_ENDPOINT),
                access_key=str(settings.MINIO_ACCESS_KEY),
                secret_key=str(settings.MINIO_SECRET_KEY),
                secure=bool(settings.MINIO_SECURE),
            )
            if not client.bucket_exists(self.bucket):
                client.make_bucket(self.bucket)
            self._minio_client = client
        return self._minio_client

    def _local_dir(self) -> Path:
        d = Path(getattr(settings, "KNOWLEDGE_IMAGE_DIR", "data/knowledge_images"))
        if not d.is_absolute():
            d = Path(__file__).resolve().parents[3] / d
        return d

    # ------------------------------------------------------------------
    # 存储接口
    # ------------------------------------------------------------------

    def save(self, storage_key: str, data: bytes, content_type: str) -> str:
        """写入图片，返回 storage_key（幂等，同 key 覆盖）。"""
        if self.use_minio:
            client = self._get_minio()
            client.put_object(
                self.bucket,
                storage_key,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
        else:
            dest = self._local_dir() / storage_key
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        return storage_key

    def get_bytes(self, storage_key: str) -> bytes:
        if self.use_minio:
            client = self._get_minio()
            resp = None
            try:
                resp = client.get_object(self.bucket, storage_key)
                return resp.read()
            finally:
                if resp is not None:
                    resp.close()
                    resp.release_conn()
        else:
            p = self._local_dir() / storage_key
            if not p.is_file():
                raise FileNotFoundError(storage_key)
            return p.read_bytes()

    def presign_url(self, storage_key: str, expires: Optional[int] = None) -> Optional[str]:
        """MinIO 预签名 URL；本地模式返回 None（走 API 端点流式读取）。"""
        if not self.use_minio:
            return None
        ttl = int(expires or getattr(settings, "IMAGE_URL_TTL_SECONDS", 3600))
        return self._get_minio().presigned_get_object(
            self.bucket, storage_key, expires=timedelta(seconds=ttl)
        )

    def delete(self, storage_key: str) -> None:
        if self.use_minio:
            self._get_minio().remove_object(self.bucket, storage_key)
        else:
            p = self._local_dir() / storage_key
            if p.is_file():
                p.unlink()
