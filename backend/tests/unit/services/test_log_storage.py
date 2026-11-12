"""日志存储抽象（本地 / MinIO 回退）。"""

import pytest

from app.core.config import settings
from app.services.diagnostics.log_storage import LogStorage, LogStorageError


class TestLocalLogStorage:
    def test_local_passthrough(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "MINIO_ENABLED", False)
        storage = LogStorage()
        source = tmp_path / "a.log"
        source.write_text("hello", encoding="utf-8")

        reference = storage.save(source, "a.log")
        assert reference == str(source)
        assert storage.materialize(reference) == source

        storage.delete(reference)
        assert not source.exists()

    def test_minio_reference_unavailable_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "MINIO_ENABLED", False)
        storage = LogStorage()
        with pytest.raises(LogStorageError):
            storage.materialize("minio://bucket/logs/x.log")
