"""日志关键字定位测试（P1 步骤 4 后半）。"""

from datetime import datetime

from app.services.chat.log_locator import locate_bytes, locate_lines, locate_with_manifest
from app.services.chat.log_patterns import LogPattern
from app.services.diagnostics.log_timeline import scan_bytes

LOG = "\n".join(
    [f"[2026-08-02 14:{minute:02d}:00]  [APP] pri:  heartbeat ok" for minute in range(0, 20)]
    + ["[2026-08-02 14:20:00]  [NL668_4G] pri:  AT+CGDCONT? returned empty"]
    + ["[2026-08-02 14:20:01]  [NL668_4G] pri:  NMEA no signal, retry"]
    + [f"[2026-08-02 14:{minute:02d}:30]  [APP] pri:  heartbeat ok" for minute in range(21, 40)]
    + ["[2026-08-02 15:30:00]  [APP] pri:  AT+CGDCONT? ok / NMEA locked"]
) + "\n"

PATTERNS = [
    LogPattern(pattern="AT+CGDCONT", type="at_cmd"),
    LogPattern(pattern="NMEA", type="literal"),
]


def test_locate_finds_hits_and_reports_counts():
    result = locate_lines(LOG.splitlines(), PATTERNS, context_lines=2)

    assert result.has_hits
    assert result.pattern_hits["at+cgdcont"] == 2
    assert result.pattern_hits["nmea"] == 2
    assert result.matched_lines == 3


def test_blocks_merge_overlapping_context():
    result = locate_lines(LOG.splitlines(), PATTERNS, context_lines=2)
    # 14:20 的两条命中相邻 → 合并成一个块；15:30 单独一块
    assert len(result.blocks) == 2
    assert result.blocks[0].line_start <= 21 <= result.blocks[0].line_end


def test_blocks_ranked_by_distinct_patterns():
    result = locate_lines(LOG.splitlines(), PATTERNS, context_lines=2)
    top = result.blocks[0]
    assert set(top.patterns) == {"AT+CGDCONT", "NMEA"}
    assert top.hits >= 2


def test_context_is_clamped_at_edges():
    lines = ["[2026-08-02 14:00:00]  [APP] NMEA start"] + ["[2026-08-02 14:00:01]  [APP] ok"] * 3
    result = locate_lines(lines, [LogPattern(pattern="NMEA", type="literal")], context_lines=20)
    block = result.blocks[0]
    assert block.line_start == 1
    assert block.line_end == 4


def test_zero_hits_returns_empty_and_missing_list():
    result = locate_lines(LOG.splitlines(), [LogPattern(pattern="P_AV_AO_CHN", type="param")])
    assert result.blocks == []
    assert result.missing_patterns([LogPattern(pattern="P_AV_AO_CHN", type="param")]) == ["P_AV_AO_CHN"]


def test_time_window_filters_lines():
    data = LOG.encode("utf-8")
    result = locate_bytes(
        data, PATTERNS,
        start=datetime(2026, 8, 2, 15, 25), end=datetime(2026, 8, 2, 15, 35),
    )
    assert result.pattern_hits == {"at+cgdcont": 1, "nmea": 1}
    assert len(result.blocks) == 1


def test_locate_with_manifest_reads_only_window():
    data = LOG.encode("utf-8")
    manifest = scan_bytes(data)
    read_calls = []

    def read_range(start, end):
        read_calls.append((start, end))
        return data[start:end]

    result = locate_with_manifest(
        read_range, manifest, PATTERNS,
        start=datetime(2026, 8, 2, 15, 25), end=datetime(2026, 8, 2, 15, 35),
    )

    assert result.has_hits
    assert read_calls, "应按 manifest 的字节区间分段读取"
    total_read = sum(end - start for start, end in read_calls)
    assert total_read < len(data), "只应读取时间窗对应的字节"


def test_limit_caps_blocks():
    lines: list[str] = []
    for minute in range(0, 12):
        filler = "NMEA timeout" if minute % 4 == 0 else "heartbeat ok"
        lines.append(f"[2026-08-02 14:{minute:02d}:00]  [APP] pri:  {filler}")

    result = locate_lines(lines, [LogPattern(pattern="NMEA", type="literal")], context_lines=0, limit=2)

    assert len(result.blocks) == 2
    assert result.pattern_hits["nmea"] == 3
