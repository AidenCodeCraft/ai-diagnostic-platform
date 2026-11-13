"""LogStorage 自动创建 MinIO bucket 的单元测试（不依赖真实 MinIO/网络）。

覆盖：
1. `MINIO_ENABLED=false` → 不构造客户端、不连接，走本地回退；
2. bucket 已存在 → 不调用 `make_bucket`；
3. bucket 不存在 → 自动 `make_bucket` 1 次，`remote_available=True`；
4. 并发首次启动：`make_bucket` 抛“已存在”类错误 → 重查 `bucket_exists` 后仍可用（幂等）；
5. 建桶权限/网络错误 → `remote_available=False`，`save()` 回退本地路径；
6. bucket 检查本身失败（连接失败）→ 回退本地，不抛异常。
"""

import sys
import types

import pytest

from app.core.config import settings
from app.services.diagnostics.log_storage import LogStorage

BUCKET = "diagnostic-logs"
CREATED: list = []


class FakeS3Error(Exception):
    """模拟 minio.error.S3Error（只需要 code 属性）。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FakeMinioBase:
    """可被 `from minio import Minio` 拿到的 fake 客户端基类。"""

    def __init__(self, endpoint, access_key=None, secret_key=None, secure=False):
        self.endpoint = endpoint
        self.access_key = access_key
        self.secure = secure
        self.calls: list[tuple[str, str]] = []
        CREATED.append(self)

    def bucket_exists(self, bucket):  # noqa: D401 - 子类实现
        raise NotImplementedError

    def make_bucket(self, bucket):
        raise NotImplementedError


@pytest.fixture(autouse=True)
def _reset_created():
    CREATED.clear()
    yield
    CREATED.clear()


def _install_fake_minio(monkeypatch, client_cls) -> None:
    fake_module = types.ModuleType("minio")
    fake_module.Minio = client_cls  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "minio", fake_module)


def _enable_minio(monkeypatch, bucket: str = BUCKET) -> None:
    monkeypatch.setattr(settings, "MINIO_ENABLED", True)
    monkeypatch.setattr(settings, "MINIO_BUCKET", bucket)
    monkeypatch.setattr(settings, "MINIO_ENDPOINT", "fake-minio:9000")
    monkeypatch.setattr(settings, "MINIO_ACCESS_KEY", "test-key")
    monkeypatch.setattr(settings, "MINIO_SECRET_KEY", "test-secret")
    monkeypatch.setattr(settings, "MINIO_SECURE", False)


def _save_local(tmp_path) -> tuple[object, str]:
    source = tmp_path / "sample.log"
    source.write_text("log line\n", encoding="utf-8")
    storage = LogStorage()
    return source, storage.save(source, source.name)


# ----------------------------------------------------------------------
# 1. 关闭 MinIO：不构造客户端、不连接
# ----------------------------------------------------------------------


def test_disabled_minio_does_not_create_client(monkeypatch, tmp_path):
    class _BoomClient(FakeMinioBase):
        def __init__(self, *args, **kwargs):
            raise AssertionError("MINIO_ENABLED=false 时不应构造 MinIO 客户端")

    _install_fake_minio(monkeypatch, _BoomClient)
    monkeypatch.setattr(settings, "MINIO_ENABLED", False)

    source, reference = _save_local(tmp_path)

    assert LogStorage().remote_available is False
    assert reference == str(source)
    assert CREATED == []


# ----------------------------------------------------------------------
# 2. bucket 已存在：不调用 make_bucket
# ----------------------------------------------------------------------


def test_existing_bucket_is_not_created(monkeypatch):
    class _Client(FakeMinioBase):
        def bucket_exists(self, bucket):
            self.calls.append(("bucket_exists", bucket))
            return True

        def make_bucket(self, bucket):
            self.calls.append(("make_bucket", bucket))

    _enable_minio(monkeypatch)
    _install_fake_minio(monkeypatch, _Client)

    storage = LogStorage()

    assert storage.remote_available is True
    assert len(CREATED) == 1
    client = CREATED[0]
    assert client.endpoint == "fake-minio:9000"
    assert client.calls == [("bucket_exists", BUCKET)]
    assert not any(name == "make_bucket" for name, _ in client.calls)


# ----------------------------------------------------------------------
# 3. bucket 不存在：自动创建 1 次
# ----------------------------------------------------------------------


def test_missing_bucket_is_created(monkeypatch):
    class _Client(FakeMinioBase):
        def bucket_exists(self, bucket):
            self.calls.append(("bucket_exists", bucket))
            return False

        def make_bucket(self, bucket):
            self.calls.append(("make_bucket", bucket))

    _enable_minio(monkeypatch)
    _install_fake_minio(monkeypatch, _Client)

    storage = LogStorage()

    assert storage.remote_available is True
    client = CREATED[0]
    assert client.calls == [("bucket_exists", BUCKET), ("make_bucket", BUCKET)]
    assert sum(1 for name, _ in client.calls if name == "make_bucket") == 1


# ----------------------------------------------------------------------
# 4. 并发首次启动：make_bucket 抛“已存在” → 重查后仍可用
# ----------------------------------------------------------------------


def test_concurrent_bucket_creation_is_idempotent(monkeypatch):
    class _RaceClient(FakeMinioBase):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.exists_count = 0

        def bucket_exists(self, bucket):
            self.exists_count += 1
            self.calls.append(("bucket_exists", bucket))
            # 首次检查：不存在；并发创建后重查：已存在
            return self.exists_count > 1

        def make_bucket(self, bucket):
            self.calls.append(("make_bucket", bucket))
            raise FakeS3Error("BucketAlreadyOwnedByYou")

    _enable_minio(monkeypatch)
    _install_fake_minio(monkeypatch, _RaceClient)

    storage = LogStorage()

    assert storage.remote_available is True
    client = CREATED[0]
    assert client.exists_count == 2, "make_bucket 失败后应重新检查 bucket_exists"
    assert client.calls == [
        ("bucket_exists", BUCKET),
        ("make_bucket", BUCKET),
        ("bucket_exists", BUCKET),
    ]


# ----------------------------------------------------------------------
# 5. 建桶权限/网络错误：回退本地（不抛异常）
# ----------------------------------------------------------------------


def test_make_bucket_failure_falls_back_to_local(monkeypatch, tmp_path):
    class _DeniedClient(FakeMinioBase):
        def bucket_exists(self, bucket):
            return False

        def make_bucket(self, bucket):
            raise FakeS3Error("AccessDenied")

    _enable_minio(monkeypatch)
    _install_fake_minio(monkeypatch, _DeniedClient)

    source, reference = _save_local(tmp_path)

    assert LogStorage().remote_available is False
    assert reference == str(source), "建桶失败应保持既有回退本地语义"


# ----------------------------------------------------------------------
# 6. bucket 检查本身失败（连接失败/认证失败）：回退本地
# ----------------------------------------------------------------------


def test_bucket_check_failure_falls_back_to_local(monkeypatch, tmp_path):
    class _BrokenClient(FakeMinioBase):
        def bucket_exists(self, bucket):
            raise RuntimeError("connection refused")

        def make_bucket(self, bucket):  # pragma: no cover - 不应被调用
            raise AssertionError("bucket_exists 失败时不应继续 make_bucket")

    _enable_minio(monkeypatch)
    _install_fake_minio(monkeypatch, _BrokenClient)

    source, reference = _save_local(tmp_path)

    assert LogStorage().remote_available is False
    assert reference == str(source)
