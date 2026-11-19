"""日志证据组装测试（P1 步骤 4 收口）。"""

from datetime import datetime

from app.services.chat.log_evidence import build_log_evidence

KB_ITEMS = [{
    "key": "1:GPS 不上报排查:0",
    "section": "GPS 不上报排查",
    "snippet": "设备不上报时先看模块 NL668_4G 是否注册，可执行 AT+CGDCONT? 检查 PDP 上下文。",
}]

LOG = "\n".join([
    "[2026-08-02 14:19:58]  [APP] pri:  heartbeat ok",
    "[2026-08-02 14:20:00]  [NL668_4G] pri:  AT+CGDCONT? returned empty",
    "[2026-08-02 14:20:05]  [NL668_4G] pri:  NMEA no signal, retry",
    "[2026-08-02 14:20:10]  [APP] pri:  heartbeat ok",
    "[2026-08-02 14:20:20]  [APP] pri:  heartbeat ok",
]) + "\n"


def test_evidence_contains_line_numbers_and_patterns():
    evidence = build_log_evidence(KB_ITEMS, LOG.encode("utf-8"), window_label="14:20")

    assert evidence.has_hits
    assert "## 日志命中（14:20）" in evidence.text
    assert "AT+CGDCONT" in evidence.text or "at+cgdcont" in evidence.text.lower()
    assert "行 " in evidence.text
    assert evidence.result.pattern_hits["at+cgdcont"] == 1


def test_zero_hits_summary_says_key_points_missing():
    unrelated_log = "\n".join([
        "[2026-08-02 14:20:00]  [APP] pri:  heartbeat ok",
        "[2026-08-02 14:20:05]  [APP] pri:  volume changed",
    ]) + "\n"
    evidence = build_log_evidence(KB_ITEMS, unrelated_log.encode("utf-8"))

    assert evidence.has_hits is False
    assert "关键点" in evidence.summary
    assert "未找到" not in evidence.summary


def test_no_log_bytes_reports_attachment_problem():
    evidence = build_log_evidence(KB_ITEMS, None)
    assert "没有可用的日志内容" in evidence.summary
    assert evidence.patterns, "模式仍应抽出，便于排查"


def test_items_without_matchable_tokens_report_missing_doc():
    items = [{"key": "2:概述:0", "section": "概述", "snippet": "本文介绍设备的整体情况。"}]
    evidence = build_log_evidence(items, LOG.encode("utf-8"))
    # 能抽出少量短语，但都不在日志里 → 走「关键点未命中」
    assert ("关键点" in evidence.summary) or ("没有可用于匹配" in evidence.summary)


def test_time_window_is_respected():
    data = (LOG + "[2026-08-02 15:40:00]  [NL668_4G] pri:  AT+CGDCONT? ok\n").encode("utf-8")
    evidence = build_log_evidence(
        KB_ITEMS, data,
        start=datetime(2026, 8, 2, 15, 35), end=datetime(2026, 8, 2, 15, 45),
    )
    assert evidence.result.pattern_hits.get("at+cgdcont") == 1
    assert evidence.result.pattern_hits.get("nmea", 0) == 0
