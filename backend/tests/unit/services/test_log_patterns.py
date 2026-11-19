"""知识库关键字抽取测试（P1 步骤 4 前半）。"""

from app.services.chat.log_patterns import (
    LogPattern,
    describe_partial_hits,
    describe_zero_hits,
    extract_patterns,
)


ITEMS = [
    {
        "key": "1:GPS 不上报排查:0",
        "section": "GPS 不上报排查",
        "snippet": (
            "### GPS 不上报排查\n"
            "设备不上报时先看模块 `NL668_4G_GetRegSta` 是否注册成功。\n"
            "可执行 AT+CGDCONT? 检查 PDP 上下文。\n"
            "参数 P_AV_AO_CHN 与 s8RegNetName 需要重点关注。\n"
            "错误码 1078 表示基站注册失败。\n"
        ),
    }
]


def test_extract_patterns_prioritises_structured_tokens():
    patterns = extract_patterns(ITEMS, question="GPS 不上报怎么办")
    types = [pattern.type for pattern in patterns]

    assert "at_cmd" in types
    assert "param" in types
    assert types == sorted(types, key=lambda t: {"at_cmd": 0, "param": 1, "module": 2, "code": 3, "literal": 4, "phrase": 5}[t])

    at_cmd = next(p for p in patterns if p.type == "at_cmd")
    assert at_cmd.pattern.upper().startswith("AT+CGDCONT")
    assert at_cmd.source_key == ITEMS[0]["key"]


def test_every_pattern_is_traceable_to_source_text():
    patterns = extract_patterns(ITEMS)
    haystack = (ITEMS[0]["snippet"] + ITEMS[0]["section"]).lower()
    for pattern in patterns:
        assert pattern.pattern.lower() in haystack, f"模式 {pattern.pattern} 不在来源文本里"


def test_patterns_are_deduplicated():
    items = ITEMS * 2
    patterns = extract_patterns(items)
    values = [pattern.pattern.lower() for pattern in patterns]
    assert len(values) == len(set(values))


def test_question_words_are_not_taken_as_literals():
    patterns = extract_patterns(ITEMS, question="GPS 不上报怎么办")
    literals = {p.pattern.lower() for p in patterns if p.type == "literal"}
    assert "gps" not in literals


def test_empty_items_yield_no_patterns():
    assert extract_patterns([]) == []


def test_zero_hit_message_mentions_patterns_not_just_not_found():
    patterns = [LogPattern(pattern="NMEA", type="literal"), LogPattern(pattern="AT+CGDCONT", type="at_cmd")]
    text = describe_zero_hits(patterns, window_label="14:20 附近")
    assert "关键点" in text
    assert "NMEA" in text
    assert "未找到" not in text


def test_zero_hit_message_without_patterns():
    assert "补充对应文档" in describe_zero_hits([])


def test_partial_hit_message_lists_misses():
    patterns = [LogPattern(pattern="NMEA", type="literal"), LogPattern(pattern="AT+CGDCONT", type="at_cmd")]
    text = describe_partial_hits(patterns, {"nmea": 3, "at+cgdcont": 0})
    assert "AT+CGDCONT" in text
    assert "NMEA" not in text


def test_no_partial_message_when_all_hit():
    patterns = [LogPattern(pattern="NMEA", type="literal")]
    assert describe_partial_hits(patterns, {"nmea": 2}) == ""
