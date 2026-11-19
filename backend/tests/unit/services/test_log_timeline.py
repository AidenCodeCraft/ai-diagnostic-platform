"""日志时间轴扫描测试（P1 步骤 2）。"""

from datetime import datetime

from app.services.diagnostics.log_timeline import (
    extract_module,
    extract_timestamp,
    scan_bytes,
    scan_stream,
)

import io

LOG = """[2026-08-02 14:21:59]  [NL668_4G_GetRegSta.. 0719] pri:  s8RegNetName:CHINA MOBILE
[2026-08-02 14:22:01]  [RMSG_SYS_AV_VOLUME.. 0418] pri:  PAM_SetParam Volume:27, 20, 20
[2026-08-02 14:59:59]  [RMSG_SYS_AV_VOLUME.. 0418] pri:  PAM_SetParam Volume:27, 20, 20
[2026-08-02 15:00:03]  [Atcmd_Decode_Cmd_R.. 0311] pri:  CPOS RECEIVE AT+CGDCONT?
       at com.example.Task.run(Task.java:42)
[2026-08-02 16:05:10]  [NL668_4G_GetRegSta.. 0719] pri:  s8RegNetName:CHINA UNICOM
""".encode("utf-8")


def test_scan_counts_and_range():
    manifest = scan_bytes(LOG)

    assert manifest.total_lines == 6
    assert manifest.parsed_lines == 5
    assert manifest.unparsed_lines == 1          # 堆栈续行没有时间戳
    assert manifest.min_ts == "2026-08-02 14:21:59"
    assert manifest.max_ts == "2026-08-02 16:05:10"
    assert manifest.size_bytes == len(LOG)
    assert manifest.encoding == "utf-8"


def test_hour_offsets_cover_each_hour():
    manifest = scan_bytes(LOG)
    assert sorted(manifest.hour_offsets) == [
        "2026-08-02 14", "2026-08-02 15", "2026-08-02 16",
    ]
    # 第一个小时的偏移必须是 0（文件开头）
    assert manifest.hour_offsets["2026-08-02 14"][0] == 0


def test_module_stats_aggregated():
    manifest = scan_bytes(LOG)
    assert manifest.module_stats["RMSG_SYS_AV_VOLUME..:0418"] == 2
    assert manifest.module_stats["NL668_4G_GetRegSta..:0719"] == 2


def test_contains_time_point():
    manifest = scan_bytes(LOG)
    assert manifest.contains(datetime(2026, 8, 2, 15, 0)) is True
    assert manifest.contains(datetime(2026, 8, 2, 13, 0)) is False
    # 容差覆盖 1 小时前
    assert manifest.contains(datetime(2026, 8, 2, 13, 30), tolerance_minutes=60) is True
    assert manifest.contains(None) is None


def test_window_offsets_allow_range_read():
    manifest = scan_bytes(LOG)
    windows = manifest.window_offsets(
        datetime(2026, 8, 2, 14, 30), datetime(2026, 8, 2, 15, 10),
    )
    assert [key for key, _, _ in windows] == ["2026-08-02 14", "2026-08-02 15"]

    first_key, start, end = windows[0]
    chunk = LOG[start:end].decode("utf-8")
    assert "14:59:59" in chunk
    assert "15:00:03" not in chunk

    second_key, start2, end2 = windows[1]
    chunk2 = LOG[start2:end2].decode("utf-8")
    assert "15:00:03" in chunk2
    assert "16:05:10" not in chunk2


def test_stream_with_chunk_boundaries():
    """一行被 read() 边界切开时不能丢也不能重复计数。"""
    stream = io.BytesIO(LOG)
    original_read = stream.read

    def tiny_read(size=-1):
        return original_read(7 if size in (-1, 4096, 65536) else size)

    stream.read = tiny_read  # type: ignore[assignment]
    manifest = scan_stream(stream)
    assert manifest.total_lines == 6
    assert manifest.parsed_lines == 5


def test_extractors_tolerate_garbage():
    assert extract_timestamp("no timestamp here") is None
    assert extract_module("no module here") is None
    assert extract_timestamp("[2026-13-45 99:99:99] invalid") is None
