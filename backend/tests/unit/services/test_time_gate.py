"""时间窗闸门测试（P1 步骤 3）。"""

from datetime import datetime

from app.services.chat.time_gate import check_time_window, resolve_time_choice
from app.services.diagnostics.log_timeline import scan_bytes

LOG = """[2026-08-02 09:00:00]  [APP] pri:  boot ok
[2026-08-02 12:00:05]  [SYS] pri:  watchdog reset triggered
""".encode("utf-8")

WINDOWS = [{
    "start": "2026-08-02 12:00:05",
    "end": "2026-08-02 12:00:09",
    "count": 2,
    "weight": 3,
    "samples": ["watchdog reset triggered"],
}]


def _analysis():
    manifest = scan_bytes(LOG)
    return {"timeline": manifest.to_dict(), "error_windows": WINDOWS}


def test_time_inside_coverage_passes():
    slots = {"time": "2026-08-02 10:30", "city": "深圳", "device": "L10", "phenomenon": "重启", "attachment": True}
    assert check_time_window(slots, _analysis()) is None


def test_time_outside_coverage_returns_options():
    slots = {"time": "2026-08-03 10:00", "city": "深圳", "device": "L10", "phenomenon": "重启", "attachment": True}
    result = check_time_window(slots, _analysis())

    assert result is not None
    assert result["awaiting"] == "time_choice"
    assert "日志覆盖的时间范围" in result["reply"]
    assert result["options"][-1]["manual"] is True
    assert result["coverage"]["min"].startswith("2026-08-02")


def test_missing_timeline_skips_gate():
    slots = {"time": "2026-08-03 10:00"}
    assert check_time_window(slots, {}) is None
    assert check_time_window(slots, None) is None


def test_missing_slot_time_skips_gate():
    assert check_time_window({"time": None}, _analysis()) is None
    assert check_time_window({}, _analysis()) is None


def test_resolve_time_choice_pads_five_minutes():
    window = resolve_time_choice({"start": "2026-08-02 12:00:05", "end": "2026-08-02 12:00:09"})
    assert window == {"start": "2026-08-02 11:55:05", "end": "2026-08-02 12:05:09"}
    assert resolve_time_choice(None) is None
    assert resolve_time_choice({"start": "bad"}) is None
