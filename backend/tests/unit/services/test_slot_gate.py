"""槽位闸门测试（P1 步骤 1）。"""

from datetime import datetime

import pytest

from app.services.chat.slot_gate import (
    build_slot_clarification,
    extract_city,
    extract_device,
    extract_phenomenon,
    extract_slots,
    merge_slots,
    parse_beijing_time,
)

NOW = datetime(2026, 8, 3, 10, 0)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("设备在 2026-08-02 14:22 黑屏", datetime(2026, 8, 2, 14, 22)),
        ("2026/08/02 14:22:31 的时候断网", datetime(2026, 8, 2, 14, 22)),
        ("8月2日14:22 起不上报", datetime(2026, 8, 2, 14, 22)),
        ("8月2日下午3点20 出问题", datetime(2026, 8, 2, 15, 20)),
    ],
)
def test_parse_absolute_time(text, expected):
    assert parse_beijing_time(text, now=NOW) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("昨天下午3点开始黑屏", datetime(2026, 8, 2, 15, 0)),
        ("今天 09:15 断网", datetime(2026, 8, 3, 9, 15)),
        ("前日凌晨1点20离线", datetime(2026, 8, 1, 1, 20)),
    ],
)
def test_parse_relative_time(text, expected):
    assert parse_beijing_time(text, now=NOW) == expected


def test_parse_time_returns_none_without_time():
    assert parse_beijing_time("设备黑屏了", now=NOW) is None
    assert parse_beijing_time("", now=NOW) is None


def test_extract_city_from_whitelist_and_suffix():
    assert extract_city("深圳的 L10 黑屏") == "深圳"
    assert extract_city("在长沙市某仓库") == "长沙"
    assert extract_city("现场设备异常") is None


def test_extract_device_prefers_hint_and_ignores_years():
    assert extract_device("L10 黑屏") == "L10"
    assert extract_device("型号：NL668 不上报") == "NL668"
    assert extract_device("2026 年 8 月 2 日黑屏") is None


def test_extract_phenomenon():
    assert extract_phenomenon("设备反复重启") in ("重启", "反复重启")
    assert extract_phenomenon("一切正常") is None


def test_extract_slots_complete():
    result = extract_slots(
        "深圳 L10 设备 2026-08-02 14:22 开始黑屏",
        has_attachment=True,
        now=NOW,
    )
    assert result.complete is True
    assert result.slots["city"] == "深圳"
    assert result.slots["device"] == "L10"
    assert result.slots["time"] == "2026-08-02 14:22"
    assert result.slots["attachment"] is True


def test_extract_slots_missing_order_is_stable():
    result = extract_slots("设备黑屏了", has_attachment=False, now=NOW)
    assert result.missing == ["city", "device", "time", "attachment"]
    assert result.complete is False


def test_clarification_asks_all_missing_at_once():
    text = build_slot_clarification(["city", "time", "attachment"])
    assert "城市" in text and "时间点（北京时间）" in text and "日志附件" in text
    assert "北京时间" in text  # 明确时区口径
    # 不是连环追问：三条缺失在同一段里
    assert text.count("还需要你补充") == 1


def test_merge_slots_keeps_existing_when_new_is_empty():
    merged = merge_slots({"city": "深圳", "device": "L10"}, {"city": None, "time": "2026-08-02 14:22"})
    assert merged == {"city": "深圳", "device": "L10", "time": "2026-08-02 14:22"}
