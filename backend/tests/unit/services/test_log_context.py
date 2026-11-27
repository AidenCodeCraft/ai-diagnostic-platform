"""日志上下文装配测试（P1 步骤 5 前置）。"""

from datetime import datetime

from app.services.chat.log_context import (
    build_log_context,
    read_window,
    resolve_window,
)
from app.services.diagnostics.log_timeline import scan_bytes

LOG = "\n".join([
    f"[2026-08-02 14:{minute:02d}:00]  [APP] pri:  heartbeat ok"
    for minute in range(0, 30)
]) + "\n[2026-08-02 14:20:00]  [NL668_4G] pri:  AT+CGDCONT? empty\n" + (
    "\n".join([
        f"[2026-08-02 15:{minute:02d}:00]  [APP] pri:  heartbeat ok"
        for minute in range(0, 30)
    ]) + "\n"
)


def test_resolve_window_from_slot_time():
    start, end, label = resolve_window({"time": "2026-08-02 14:20"})
    assert start == datetime(2026, 8, 2, 13, 50)
    assert end == datetime(2026, 8, 2, 14, 50)
    assert "±30" in label


def test_resolve_window_prefers_selected_window():
    context = {"resolved_time_window": {"start": "2026-08-02 14:15:00", "end": "2026-08-02 14:25:00"}}
    start, end, _ = resolve_window({"time": "2026-08-02 14:20"}, context)
    assert start == datetime(2026, 8, 2, 14, 15)
    assert end == datetime(2026, 8, 2, 14, 25)


def test_resolve_window_without_time():
    assert resolve_window({}) == (None, None, "")


def test_read_window_uses_manifest_offsets(tmp_path):
    path = tmp_path / "app.log"
    path.write_bytes(LOG.encode("utf-8"))
    manifest = scan_bytes(LOG.encode("utf-8"))

    chunk = read_window(
        str(path), manifest, datetime(2026, 8, 2, 14, 19), datetime(2026, 8, 2, 14, 21),
    )

    assert chunk is not None
    text = chunk.decode("utf-8")
    assert "AT+CGDCONT" in text
    assert "15:29:00" not in text, "时间窗外的数据不应被读取"
    assert len(chunk) < len(LOG.encode("utf-8"))


def test_read_window_without_manifest_reads_file(tmp_path):
    path = tmp_path / "app.log"
    path.write_bytes(LOG.encode("utf-8"))

    chunk = read_window(str(path), None, None, None)
    assert chunk == LOG.encode("utf-8")


def test_read_window_missing_file_returns_none(tmp_path):
    assert read_window(str(tmp_path / "nope.log"), None, None, None) is None


def test_build_log_context_requires_reference_and_time():
    analysis = {"reference": "/tmp/x.log"}
    assert build_log_context({"time": "2026-08-02 14:20"}, {}) is None
    assert build_log_context({}, analysis) is None


def test_build_log_context_with_injected_loader():
    analysis = {"reference": "minio://bucket/key", "timeline": scan_bytes(LOG.encode("utf-8")).to_dict()}
    captured = {}

    def loader(reference, manifest, start, end):
        captured["reference"] = reference
        captured["start"] = start
        return b"line"

    context = build_log_context({"time": "2026-08-02 14:20"}, analysis, loader=loader)
    assert context is not None
    assert context.data == b"line"
    assert captured["reference"] == "minio://bucket/key"
    assert context.start == datetime(2026, 8, 2, 13, 50)
