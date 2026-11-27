"""对象存储布局与预签名测试（P3 存储治理）。"""

from datetime import timedelta

from app.services.diagnostics.log_storage import LogStorage


class FakeClient:
    def __init__(self):
        self.puts = []
        self.presigns = []

    def fput_object(self, bucket, key, path):
        self.puts.append((bucket, key, path))

    def presigned_get_object(self, bucket, key, expires=None):
        self.presigns.append((bucket, key, expires))
        return f"https://minio.example/{bucket}/{key}?sig=abc"


def build_storage(ttl=900, client=None):
    storage = object.__new__(LogStorage)
    storage.enabled = True
    storage.bucket = "diag-logs"
    storage.presign_ttl = ttl
    storage._client = client or FakeClient()
    return storage


def test_save_uses_project_and_date_layout(tmp_path):
    path = tmp_path / "a.log"
    path.write_text("x")
    storage = build_storage()

    reference = storage.save(path, "a.log", project_id=7)

    bucket, key, _ = storage._client.puts[0]
    assert bucket == "diag-logs"
    assert key.startswith("logs/p7/"), key
    parts = key.split("/")
    assert len(parts) == 4
    assert parts[2].isdigit() and len(parts[2]) == 8
    assert parts[3].endswith("_a.log")
    assert reference == f"minio://diag-logs/{key}"


def test_save_without_project_uses_p0(tmp_path):
    path = tmp_path / "a.log"
    path.write_text("x")
    storage = build_storage()

    storage.save(path, "a.log")

    _, key, _ = storage._client.puts[0]
    assert key.startswith("logs/p0/")


def test_presigned_get_uses_default_ttl():
    storage = build_storage(ttl=900)

    url = storage.presigned_get("minio://diag-logs/logs/p7/20260101/abc.log")

    assert url.startswith("https://minio.example/")
    bucket, key, expires = storage._client.presigns[0]
    assert bucket == "diag-logs"
    assert key == "logs/p7/20260101/abc.log"
    assert expires == timedelta(seconds=900)


def test_presigned_get_honours_override_ttl():
    storage = build_storage()
    storage.presigned_get("minio://diag-logs/k.log", ttl_seconds=60)
    assert storage._client.presigns[0][2] == timedelta(seconds=60)


def test_presigned_get_rejects_non_object_reference():
    storage = build_storage()
    assert storage.presigned_get("/var/data/raw/a.log") is None
    assert storage.presigned_get("") is None
    assert storage._client.presigns == []


def test_presigned_get_returns_none_when_remote_unavailable():
    storage = build_storage()
    storage._client = None
    assert storage.presigned_get("minio://diag-logs/k.log") is None
