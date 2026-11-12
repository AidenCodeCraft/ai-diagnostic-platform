"""MinIO 真实对象存储集成测试（默认 skip，不阻塞 CI）。

门槛（二者满足其一即可运行）：
    RUN_REAL_MINIO=1

仅在显式开启时执行；未设置环境变量时整模块 skip；设置了但连不上 MinIO
（如本地未启动 docker compose minio）时同样 skip，而不是 fail。

连接参数（host 侧，默认直连 docker compose 暴露的 localhost:9000）：
    MINIO_VERIFY_ENDPOINT  默认 localhost:9000（不要用容器内网名 minio:9000）
    MINIO_ACCESS_KEY       默认 minioadmin
    MINIO_SECRET_KEY       默认 minioadmin
    MINIO_VERIFY_SECURE    "1"/"true" 时使用 HTTPS
    MINIO_BUCKET           默认 diagnostic-logs
    MINIO_KNOWLEDGE_BUCKET 默认 knowledge-images

运行示例（在 backend/ 目录下）：
    RUN_REAL_MINIO=1 ..\\.venv\\Scripts\\python.exe -m pytest \\
        tests/integration/services/test_minio_real.py -v
"""

from __future__ import annotations

import hashlib
import io
import os
import uuid
from datetime import timedelta
from pathlib import Path

import pytest

RUN_REAL_MINIO = os.getenv("RUN_REAL_MINIO", "").strip().lower() in ("1", "true", "yes", "on")
SKIP_REASON = "真实 MinIO 集成测试默认跳过；设置 RUN_REAL_MINIO=1 且 localhost:9000 可用来启用"

pytestmark = pytest.mark.skipif(not RUN_REAL_MINIO, reason=SKIP_REASON)


# ----------------------------------------------------------------------
# Helpers / fixtures
# ----------------------------------------------------------------------


def _endpoint() -> str:
    return os.getenv("MINIO_VERIFY_ENDPOINT", os.getenv("MINIO_ENDPOINT", "localhost:9000"))


def _secure() -> bool:
    return os.getenv("MINIO_VERIFY_SECURE", "0").strip().lower() in ("1", "true", "yes", "on")


def _make_client():
    from minio import Minio

    return Minio(
        _endpoint(),
        access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        secure=_secure(),
    )


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


@pytest.fixture(scope="module")
def client():
    """真实 MinIO 客户端；不可达时 skip（连接失败不应让 CI fail）。"""
    try:
        c = _make_client()
        c.list_buckets()
    except Exception as exc:  # noqa: BLE001 - 连接失败 = skip
        pytest.skip(f"MinIO 不可达（{_endpoint()}）: {exc}")
    return c


@pytest.fixture(scope="module")
def buckets(client):
    """确保测试所需 bucket 存在（仅创建缺失的 bucket）。"""
    names = (
        os.getenv("MINIO_BUCKET", "diagnostic-logs"),
        os.getenv("MINIO_KNOWLEDGE_BUCKET", "knowledge-images"),
    )
    for name in names:
        if not client.bucket_exists(name):
            client.make_bucket(name)
    return {"log": names[0], "image": names[1]}


@pytest.fixture()
def s3_error():
    from minio.error import S3Error

    return S3Error


@pytest.fixture()
def minio_settings(monkeypatch):
    """把后端 settings 指向 host 侧真实 MinIO（不依赖 Docker 内网名）。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "MINIO_ENABLED", True)
    monkeypatch.setattr(settings, "MINIO_ENDPOINT", _endpoint())
    monkeypatch.setattr(settings, "MINIO_ACCESS_KEY", os.getenv("MINIO_ACCESS_KEY", "minioadmin"))
    monkeypatch.setattr(settings, "MINIO_SECRET_KEY", os.getenv("MINIO_SECRET_KEY", "minioadmin"))
    monkeypatch.setattr(settings, "MINIO_SECURE", _secure())
    monkeypatch.setattr(settings, "MINIO_BUCKET", os.getenv("MINIO_BUCKET", "diagnostic-logs"))
    monkeypatch.setattr(
        settings, "MINIO_KNOWLEDGE_BUCKET", os.getenv("MINIO_KNOWLEDGE_BUCKET", "knowledge-images")
    )
    return settings


def _remove_quietly(client, bucket: str, key: str) -> None:
    try:
        client.remove_object(bucket, key)
    except Exception:  # noqa: BLE001
        pass


# ----------------------------------------------------------------------
# 1. S3 SDK 直连
# ----------------------------------------------------------------------


def test_bucket_exists(client, buckets):
    for name in buckets.values():
        assert client.bucket_exists(name), f"bucket 不存在: {name}"


def test_sdk_put_get_stat_presign_remove(client, buckets, s3_error):
    """put_object → stat（size/etag）→ get 逐字节一致 → 预签名 GET → remove 后消失。"""
    import httpx

    bucket = buckets["log"]
    key = f"_pytest/minio-{uuid.uuid4().hex}.bin"
    payload = b"PYTEST-MINIO\x00" * 128 + uuid.uuid4().bytes
    try:
        client.put_object(
            bucket, key, io.BytesIO(payload), length=len(payload),
            content_type="application/octet-stream",
        )

        stat = client.stat_object(bucket, key)
        assert stat.size == len(payload)
        assert (stat.etag or "").strip('"') == _md5(payload)

        resp = client.get_object(bucket, key)
        try:
            downloaded = resp.read()
        finally:
            resp.close()
            resp.release_conn()
        assert downloaded == payload

        url = client.presigned_get_object(bucket, key, expires=timedelta(minutes=5))
        presp = httpx.get(url, timeout=10.0)
        assert presp.status_code == 200
        assert presp.content == payload

        client.remove_object(bucket, key)
        with pytest.raises(s3_error):
            client.stat_object(bucket, key)
    finally:
        _remove_quietly(client, bucket, key)


# ----------------------------------------------------------------------
# 2. 后端 LogStorage 真连
# ----------------------------------------------------------------------


def test_log_storage_save_materialize_delete(client, buckets, s3_error, minio_settings, tmp_path):
    from app.services.diagnostics.log_storage import LogStorage

    storage = LogStorage()
    assert storage.remote_available is True
    assert storage.bucket == buckets["log"]

    content = (
        "2026-11-12 10:00:00.000 1 2 E AndroidRuntime: pytest minio roundtrip\n"
        "2026-11-12 10:00:01.000 1 2 I System.out: done\n"
    ).encode("utf-8")
    local_file = tmp_path / "pytest_minio.log"
    local_file.write_bytes(content)
    reference = None
    materialized = None
    try:
        reference = storage.save(local_file, local_file.name)
        assert reference.startswith(f"minio://{buckets['log']}/logs/")

        bucket, _, key = reference[len("minio://"):].partition("/")
        stat = client.stat_object(bucket, key)
        assert stat.size == len(content)
        assert (stat.etag or "").strip('"') == _md5(content)

        materialized = Path(storage.materialize(reference))
        assert materialized.read_bytes() == content

        storage.delete(reference)
        with pytest.raises(s3_error):
            client.stat_object(bucket, key)
    finally:
        if reference and reference.startswith("minio://"):
            bucket, _, key = reference[len("minio://"):].partition("/")
            _remove_quietly(client, bucket, key)
        if materialized is not None:
            materialized.unlink(missing_ok=True)


# ----------------------------------------------------------------------
# 3. 后端 KnowledgeImageStorage 真连
# ----------------------------------------------------------------------


def test_knowledge_image_storage_roundtrip(client, buckets, s3_error, minio_settings):
    import httpx

    from app.services.knowledge.image_storage import KnowledgeImageStorage

    storage = KnowledgeImageStorage()
    assert storage.use_minio is True
    assert storage.bucket == buckets["image"]

    data = b"\x89PNG\r\n\x1a\n" + uuid.uuid4().bytes  # 内容唯一即可，存储层不做图片解码
    key = f"_pytest/{uuid.uuid4().hex}.png"
    try:
        assert storage.save(key, data, "image/png") == key

        stat = client.stat_object(buckets["image"], key)
        assert stat.size == len(data)
        assert (stat.etag or "").strip('"') == _md5(data)

        assert storage.get_bytes(key) == data

        url = storage.presign_url(key, expires=300)
        assert url and "X-Amz-Signature" in url
        presp = httpx.get(url, timeout=10.0)
        assert presp.status_code == 200
        assert presp.content == data

        storage.delete(key)
        with pytest.raises(s3_error):
            client.stat_object(buckets["image"], key)
    finally:
        _remove_quietly(client, buckets["image"], key)


# ----------------------------------------------------------------------
# 4. 回退分支保护：MINIO_ENABLED=False 时不触碰真实 MinIO
# ----------------------------------------------------------------------


def test_disabled_storage_uses_local(tmp_path, monkeypatch):
    """MINIO_ENABLED=False 时 LogStorage 走本地回退（不访问 MinIO）。"""
    from app.core.config import settings
    from app.services.diagnostics.log_storage import LogStorage

    monkeypatch.setattr(settings, "MINIO_ENABLED", False)
    storage = LogStorage()
    assert storage.remote_available is False

    local_file = tmp_path / "fallback.log"
    local_file.write_bytes(b"fallback")
    reference = storage.save(local_file, local_file.name)
    assert reference == str(local_file)
    assert storage.materialize(reference) == local_file
    storage.delete(reference)
    assert not local_file.exists()
