"""预处理产物存储 + 模板库跨进程锁测试（不依赖 MinIO）。"""

import gzip
import json

import pytest

from app.services.diagnostics.artifact_store import ArtifactStore


class FakeRemote:
    """最小对象存储替身：只实现 put_bytes/get_bytes/list_keys。"""

    def __init__(self):
        self.objects = {}

    def put_bytes(self, data, key, content_type="application/octet-stream"):
        self.objects[key] = data
        return f"minio://diag-logs/{key}"

    def get_bytes(self, key):
        return self.objects.get(key)

    def list_keys(self, prefix):
        return sorted(k for k in self.objects if k.startswith(prefix))


class DownRemote(FakeRemote):
    """存储不可用：put_bytes 返回 None，模拟 MinIO 挂掉回退本地。"""

    def put_bytes(self, data, key, content_type="application/octet-stream"):
        return None

    def get_bytes(self, key):
        return None

    def list_keys(self, prefix):
        return []


def test_put_get_list_uses_remote_first(tmp_path):
    store = ArtifactStore(storage=FakeRemote(), local_root=str(tmp_path))
    ref = store.put(7, "normalized_0.jsonl.gz", b"data")
    assert ref.startswith("minio://")
    assert store.get(7, "normalized_0.jsonl.gz") == b"data"
    assert store.list(7) == ["normalized_0.jsonl.gz"]


def test_remote_unavailable_falls_back_to_local(tmp_path):
    store = ArtifactStore(storage=DownRemote(), local_root=str(tmp_path))

    ref = store.put(9, "templates.json", b'{"a":1}')

    assert ref == str(tmp_path / "_ingest" / "9" / "templates.json")
    assert store.get(9, "templates.json") == b'{"a":1}'
    assert store.list(9) == ["templates.json"]


def test_list_merges_remote_and_local(tmp_path):
    remote = FakeRemote()
    store = ArtifactStore(storage=remote, local_root=str(tmp_path))
    store.put(3, "normalized_0.jsonl.gz", b"a")          # 远端
    local_dir = tmp_path / "_ingest" / "3"
    local_dir.mkdir(parents=True)
    (local_dir / "normalized_1.jsonl.gz").write_bytes(b"b")  # 本地

    assert store.list(3) == ["normalized_0.jsonl.gz", "normalized_1.jsonl.gz"]
    assert store.normalized_names(3) == ["normalized_0.jsonl.gz", "normalized_1.jsonl.gz"]


def test_normalized_names_filters_other_artifacts(tmp_path):
    store = ArtifactStore(storage=FakeRemote(), local_root=str(tmp_path))
    store.put(1, "templates.json", b"{}")
    store.put(1, "normalized_0.jsonl.gz", b"x")

    assert store.normalized_names(1) == ["normalized_0.jsonl.gz"]


def test_log_indexer_reads_from_artifact_store(tmp_path, monkeypatch):
    from app.worker import ingest_service as svc

    monkeypatch.setattr(svc.settings, "UPLOAD_DIR", str(tmp_path))
    # 本地分支：read_artifacts 内部会新建 ArtifactStore（真实 LogStorage），
    # 因此产物必须落在 UPLOAD_DIR 下才能被读到，这里用 DownRemote 强制本地写。
    store = ArtifactStore(storage=DownRemote(), local_root=str(tmp_path))
    records = [
        {"ts": "2026-08-02 14:22:00", "module": "NET", "text": "[NET] register failed"},
        {"ts": "2026-08-02 14:22:05", "module": "NET", "text": "[NET] register failed"},
    ]
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"
    store.put(5, "normalized_0.jsonl.gz", gzip.compress(payload.encode("utf-8")))

    from app.services.diagnostics import log_indexer

    got = log_indexer.read_artifacts(5)

    assert len(got) == 2
    assert got[0]["module"] == "NET"


def test_drain_file_lock_is_exclusive_and_released(tmp_path, monkeypatch):
    from app.worker import ingest_service as svc

    monkeypatch.setattr(svc.settings, "UPLOAD_DIR", str(tmp_path))

    with svc._drain_file_lock(timeout=1):
        with pytest.raises(svc.DrainLockTimeout):
            with svc._drain_file_lock(timeout=0.2):
                pass

    # 释放后可以再次获取
    with svc._drain_file_lock(timeout=1):
        pass


def test_stale_drain_lock_is_cleaned(tmp_path, monkeypatch):
    import os
    import time

    from app.worker import ingest_service as svc

    monkeypatch.setattr(svc.settings, "UPLOAD_DIR", str(tmp_path))
    lock_path = svc._drain_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("stale")
    old = time.time() - svc.STALE_LOCK_SECONDS - 10
    os.utime(lock_path, (old, old))

    with svc._drain_file_lock(timeout=1):
        assert lock_path.exists()

    assert not lock_path.exists()


def test_template_id_survives_lock_contention(tmp_path, monkeypatch):
    """锁被占用时不应崩，退化哈希而不是抛异常。"""
    from app.worker import ingest_service as svc

    monkeypatch.setattr(svc.settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(svc, "_DRAIN_MINER", None)
    lock_path = svc._drain_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("busy")

    tid = svc.template_id("[APP] Volume:27")

    assert tid.startswith(("d", "h:"))
