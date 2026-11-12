"""日志接入：编码探测、限行读取、压缩包解压、上传校验。"""

import gzip
import io
import zipfile

import pytest

from app.core.config import settings
from app.services.diagnostics.log_service import LogService, LogUploadError
from app.services.parser.log_reader import LogReader


class TestLogReaderEncoding:
    def test_detect_utf8(self, tmp_path):
        path = tmp_path / "a.log"
        path.write_bytes("设备日志 timeout".encode("utf-8"))
        assert LogReader().detect_encoding(path) == "utf-8"

    def test_detect_gbk_and_decode(self, tmp_path):
        path = tmp_path / "gbk.log"
        path.write_bytes("设备日志异常".encode("gbk"))
        encoding = LogReader().detect_encoding(path)
        assert encoding in ("gb18030", "gbk")
        assert "设备日志异常" in LogReader().read_all(path)

    def test_detect_utf16_bom(self, tmp_path):
        path = tmp_path / "u16.log"
        path.write_bytes("hello 日志".encode("utf-16"))
        assert LogReader().detect_encoding(path) == "utf-16"
        assert "hello 日志" in LogReader().read_all(path)


class TestLogReaderCapped:
    def test_capped_read_truncates(self, tmp_path):
        path = tmp_path / "big.log"
        path.write_text("\n".join(f"line-{i}" for i in range(10)), encoding="utf-8")
        text, truncated = LogReader().read_all_capped(path, max_lines=3)
        assert truncated is True
        assert len(text.splitlines()) == 3

    def test_capped_read_full(self, tmp_path):
        path = tmp_path / "small.log"
        path.write_text("a\nb\n", encoding="utf-8")
        text, truncated = LogReader().read_all_capped(path, max_lines=10)
        assert truncated is False
        assert text.splitlines() == ["a", "b"]


class TestLogReaderArchives:
    def test_extract_gz(self, tmp_path):
        target = tmp_path / "app.log.gz"
        target.write_bytes(gzip.compress("日志内容".encode("utf-8")))
        extracted = LogReader.extract_archive(target)
        assert extracted is not None
        path, name = extracted
        assert name == "app.log"
        assert "日志内容" in path.read_text(encoding="utf-8")

    def test_extract_zip_prefers_text(self, tmp_path):
        target = tmp_path / "bundle.zip"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("readme.bin", b"\x00\x01")
            archive.writestr("app.log", "zip 日志".encode("utf-8"))
        extracted = LogReader.extract_archive(target)
        assert extracted is not None
        path, name = extracted
        assert name == "app.log"
        assert "zip 日志" in path.read_text(encoding="utf-8")

    def test_extract_empty_zip_raises(self, tmp_path):
        target = tmp_path / "empty.zip"
        with zipfile.ZipFile(target, "w"):
            pass
        with pytest.raises(ValueError):
            LogReader.extract_archive(target)


class TestLogServiceUpload:
    def _upload(self, filename: str, payload: bytes):
        return type("FakeUpload", (), {
            "filename": filename,
            "file": io.BytesIO(payload),
        })()

    def test_upload_zip_extracts(self, db_session, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("app.log", "zip 内容".encode("utf-8"))
        log = LogService(db_session).upload_log(
            self._upload("bundle.zip", buffer.getvalue()),
        )
        assert log.filename == "app.log"
        assert "zip 内容" in open(log.file_path, encoding="utf-8").read()

    def test_upload_rejects_oversize(self, db_session, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
        monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
        payload = b"x" * (1024 * 1024 + 10)
        with pytest.raises(LogUploadError) as exc:
            LogService(db_session).upload_log(self._upload("big.log", payload))
        assert exc.value.status_code == 413

    def test_upload_rejects_binary(self, db_session, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
        with pytest.raises(LogUploadError):
            LogService(db_session).upload_log(
                self._upload("binary.log", b"\x00\x01\x02\x03"),
            )
