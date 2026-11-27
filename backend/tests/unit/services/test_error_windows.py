"""异常时段聚合测试（P1 步骤 3）。"""

from datetime import datetime

from app.services.diagnostics.error_windows import (
    AnomalyEvent,
    analyze_log_for_windows,
    build_mismatch_reply,
    build_time_choice_options,
    classify_line,
    cluster_windows,
    collect_anomalies,
    top_windows,
)

import io

LOG = """[2026-08-02 09:00:00]  [APP] pri:  system boot ok
[2026-08-02 09:05:00]  [NET] pri:  4G register failed, retry
[2026-08-02 09:05:30]  [NET] pri:  4G register failed, retry
[2026-08-02 09:06:10]  [NET] pri:  connect timeout
[2026-08-02 12:00:00]  [APP] pri:  heartbeat ok
[2026-08-02 12:00:05]  [SYS] pri:  watchdog reset triggered
[2026-08-02 12:00:09]  [APP] pri:  system reboot
[2026-08-02 12:00:11]  [SYS] pri:  assert failed in gps_task
""".encode("utf-8")


def test_classify_line_weights():
    assert classify_line("[APP] heartbeat ok") == 0
    assert classify_line("[NET] connect timeout") == 1
    assert classify_line("[SYS] watchdog reset triggered") == 2
    assert classify_line("设备重启") >= 1


def test_collect_anomalies_reads_timestamps():
    events = collect_anomalies(io.BytesIO(LOG))
    assert len(events) == 5
    assert events[0].ts == datetime(2026, 8, 2, 9, 5)


def test_cluster_windows_splits_by_gap():
    events = collect_anomalies(io.BytesIO(LOG))
    windows = cluster_windows(events, gap_seconds=120)
    assert len(windows) == 2
    assert windows[0].count == 3
    assert windows[1].count == 2


def test_top_windows_prioritises_severe_cluster():
    events = collect_anomalies(io.BytesIO(LOG))
    windows = top_windows(events, limit=2, gap_seconds=120)
    # 第二段含 watchdog + reboot，权重更高
    assert windows[0].start.hour == 12
    assert windows[0].weight > windows[1].weight


def test_options_include_manual_choice():
    events = collect_anomalies(io.BytesIO(LOG))
    options = build_time_choice_options(top_windows(events))
    assert len(options) == 3
    assert options[-1]["manual"] is True
    assert "条异常" in options[0]["label"]


def test_mismatch_reply_states_coverage():
    manifest, windows = analyze_log_for_windows(LOG)
    reply = build_mismatch_reply(manifest, datetime(2026, 8, 3, 10, 0), windows)

    assert "2026-08-02 09:00" in reply and "2026-08-02 12:00" in reply
    assert "你问的" in reply
    assert "请选择其中一个时段" in reply


def test_mismatch_reply_without_windows():
    manifest, _ = analyze_log_for_windows(LOG)
    reply = build_mismatch_reply(manifest, datetime(2026, 8, 3, 10, 0), [])
    assert "没有识别到明显异常时段" in reply


def test_anomaly_event_weight_counts_in_window():
    events = [
        AnomalyEvent(ts=datetime(2026, 8, 2, 10, 0), line="error A", weight=1),
        AnomalyEvent(ts=datetime(2026, 8, 2, 10, 0, 30), line="panic B", weight=2),
    ]
    windows = cluster_windows(events, gap_seconds=60)
    assert windows[0].count == 2
    assert windows[0].weight == 3
