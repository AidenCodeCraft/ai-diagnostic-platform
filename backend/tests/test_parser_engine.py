"""Tests for the Log Parser Engine (Commit 005)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.parser.base import BaseParser, ParsedEvent
from app.services.parser.generic_parser import GenericParser
from app.services.parser.kernel_parser import KernelLogParser
from app.services.parser.linux_parser import LinuxSyslogParser
from app.services.parser.registry import ParserRegistry
from app.services.parser.log_reader import LogReader
from app.services.parser_service import LogParserService
from app.services.rule_engine import RuleEngine
from app.schemas.parser import ParseResult, ParsedEventSchema


# ------------------------------------------------------------------
# ParsedEvent
# ------------------------------------------------------------------


def test_parsed_event_to_dict_includes_all_fields():
    event = ParsedEvent(
        raw="kernel: ERROR usb timeout",
        message="usb timeout",
        level="ERROR",
        module="usb",
        source_type="kernel",
        is_error=True,
        classification="timeout",
    )
    d = event.to_dict()
    assert d["raw"] == "kernel: ERROR usb timeout"
    assert d["level"] == "ERROR"
    assert d["module"] == "usb"
    assert d["is_error"] is True
    assert d["classification"] == "timeout"


def test_parsed_event_metadata_and_timestamp():
    from datetime import datetime

    ts = datetime(2024, 10, 1, 10, 20, 30)
    event = ParsedEvent(
        raw="test",
        timestamp=ts,
        metadata={"uptime": 123.456},
    )
    d = event.to_dict()
    assert d["timestamp"] == "2024-10-01T10:20:30"
    assert d["metadata"] == {"uptime": 123.456}


# ------------------------------------------------------------------
# LogReader
# ------------------------------------------------------------------


def test_log_reader_read_all(tmp_path: Path):
    log_file = tmp_path / "test.log"
    log_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
    reader = LogReader()
    content = reader.read_all(log_file)
    assert content == "line1\nline2\nline3\n"


def test_log_reader_read_lines_skips_empty(tmp_path: Path):
    log_file = tmp_path / "test.log"
    log_file.write_text("line1\n\nline2\n  \nline3\n", encoding="utf-8")
    reader = LogReader()
    lines = reader.read_lines(log_file)
    assert lines == ["line1", "line2", "line3"]


def test_log_reader_stream_lines(tmp_path: Path):
    log_file = tmp_path / "large.log"
    log_file.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    reader = LogReader()
    lines = list(reader.stream_lines(log_file))
    assert lines == ["a", "b", "c", "d", "e"]


def test_log_reader_size_mb(tmp_path: Path):
    log_file = tmp_path / "test.log"
    log_file.write_bytes(b"x" * 1024 * 1024)  # 1 MB
    reader = LogReader()
    assert 0.9 < reader.read_size_mb(log_file) < 1.1


def test_log_reader_is_large(tmp_path: Path):
    log_file = tmp_path / "test.log"
    log_file.write_bytes(b"x" * 100)  # tiny
    reader = LogReader()
    assert reader.is_large(log_file, threshold_mb=1) is False


def test_log_reader_file_not_found():
    reader = LogReader()
    with pytest.raises(FileNotFoundError):
        reader.read_all("/nonexistent/path.log")


# ------------------------------------------------------------------
# GenericParser
# ------------------------------------------------------------------


def test_generic_parser_extracts_error():
    parser = GenericParser()
    event = parser.parse_line("ERROR usb: device timeout while reading descriptor")
    assert event.level == "ERROR"
    assert event.module == "usb"
    assert event.is_error is True
    assert event.classification == "timeout"


def test_generic_parser_fallback():
    parser = GenericParser()
    event = parser.parse_line("just some random text")
    assert event.level == "INFO"
    assert event.module == "system"
    assert event.is_error is False
    assert event.classification == "normal"


def test_generic_parser_classifies_memory_error():
    parser = GenericParser()
    event = parser.parse_line("segfault at 0x00000000 ip 0x00400500")
    assert event.is_error is True
    assert event.classification == "memory"


def test_generic_parser_multi_line():
    parser = GenericParser()
    text = (
        "INFO systemd: starting service\n"
        "ERROR ext4: failed to write inode\n"
        "WARN network: connection timeout\n"
    )
    events = parser.parse_text(text)
    assert len(events) == 3
    assert events[0].level == "INFO"
    assert events[1].is_error is True
    assert events[1].classification == "filesystem"
    assert events[2].level == "WARN"


# ------------------------------------------------------------------
# LinuxSyslogParser
# ------------------------------------------------------------------


def test_linux_parser_traditional_format():
    parser = LinuxSyslogParser()
    event = parser.parse_line("Oct  1 10:20:30 webserver sshd[1234]: ERROR Failed password for root")
    assert event.source_type == "linux_syslog"
    assert event.level == "ERROR"
    assert event.is_error is True
    assert event.module == "sshd"


def test_linux_parser_iso_format():
    parser = LinuxSyslogParser()
    event = parser.parse_line("2024-10-01T10:20:30Z myhost nginx[42]: 192.168.1.1 - GET /api 200")
    assert event.source_type == "linux_syslog"
    assert event.module == "nginx"
    assert event.is_error is False


def test_linux_parser_detect():
    parser = LinuxSyslogParser()
    assert parser.can_parse("Oct  1 10:20:30 myhost process[1]: test") is True
    assert parser.can_parse("[ 123.456] kernel message") is False  # kernel format


# ------------------------------------------------------------------
# KernelLogParser
# ------------------------------------------------------------------


def test_kernel_parser_dmesg_format():
    parser = KernelLogParser()
    event = parser.parse_line("[  123.456789] usb 1-1: device not responding")
    assert event.source_type == "kernel"
    assert event.module == "usb"
    assert event.is_error is True
    assert event.classification == "timeout"
    assert event.metadata.get("uptime_seconds") == 123.456789


def test_kernel_parser_oops():
    parser = KernelLogParser()
    event = parser.parse_line("[   45.000] BUG: unable to handle kernel NULL pointer dereference")
    assert event.is_error is True
    assert event.classification in ("memory", "unknown")


def test_kernel_parser_ext4_error():
    parser = KernelLogParser()
    event = parser.parse_line("[   99.000] EXT4-fs error (device sda1): ext4_find_entry")
    assert event.module in ("ext4", "kernel")
    assert event.is_error is True
    assert "ext4" in event.classification.lower() or "filesystem" in event.classification.lower()


def test_kernel_parser_level_prefix():
    parser = KernelLogParser()
    event = parser.parse_line("<3>[  10.000] usb 2-1: device descriptor read/64, error -71")
    assert event.level == "ERROR"


def test_kernel_parser_detect():
    parser = KernelLogParser()
    assert parser.can_parse("[    1.000] Booting Linux kernel") is True
    assert parser.can_parse("kernel: init process started") is True


# ------------------------------------------------------------------
# ParserRegistry
# ------------------------------------------------------------------


def test_registry_auto_detects_kernel_line():
    registry = ParserRegistry()
    parser = registry.detect("[  123.456] usb 1-1: device timeout")
    assert isinstance(parser, KernelLogParser)


def test_registry_auto_detects_syslog_line():
    registry = ParserRegistry()
    parser = registry.detect("Oct  1 10:20:30 myhost sshd: login failed")
    assert isinstance(parser, LinuxSyslogParser)


def test_registry_falls_back_to_generic():
    registry = ParserRegistry()
    parser = registry.detect("just random log text here")
    assert isinstance(parser, GenericParser)


def test_registry_parse_text_mixed_formats():
    registry = ParserRegistry()
    text = (
        "[    1.234] kernel: usb init\n"
        "Oct  1 10:20:30 host app: service started\n"
        "random application log\n"
    )
    events = registry.parse_text(text)
    assert len(events) == 3
    assert events[0].source_type == "kernel"
    assert events[1].source_type == "linux_syslog"
    assert events[2].source_type == "generic"


def test_registry_force_source():
    registry = ParserRegistry()
    # Force kernel parser on a non-kernel line -> it should still try to parse
    event = registry.parse_line("some text here", force_source="kernel")
    assert event.source_type == "kernel"


def test_registry_invalid_force_source():
    registry = ParserRegistry()
    with pytest.raises(ValueError, match="No parser registered"):
        registry.parse_line("test", force_source="nonexistent")


# ------------------------------------------------------------------
# LogParserService (backward compat)
# ------------------------------------------------------------------


def test_log_parser_service_backward_compat(tmp_path: Path):
    log_file = tmp_path / "test.log"
    log_file.write_text(
        "ERROR usb: device timeout\n"
        "INFO system: startup ok\n",
        encoding="utf-8",
    )

    service = LogParserService()
    events = service.parse_file(log_file)
    assert len(events) == 2
    assert events[0]["level"] == "ERROR"
    assert events[0]["is_error"] is True
    assert events[1]["level"] == "INFO"


def test_log_parser_service_structured(tmp_path: Path):
    log_file = tmp_path / "test.log"
    log_file.write_text("[   1.000] usb 1-1: timeout\n", encoding="utf-8")

    service = LogParserService()
    events = service.parse_structured(log_file)
    assert len(events) == 1
    assert isinstance(events[0], ParsedEvent)
    assert events[0].source_type == "kernel"


def test_log_parser_service_streaming(tmp_path: Path):
    log_file = tmp_path / "test.log"
    lines = [f"line {i}\n" for i in range(100)]
    log_file.write_text("".join(lines), encoding="utf-8")

    service = LogParserService()
    events = service.stream_parse(log_file)
    assert len(events) == 100


# ------------------------------------------------------------------
# ParseResult Schema
# ------------------------------------------------------------------


def test_parse_result_from_events():
    events = [
        ParsedEvent(raw="e1", level="ERROR", module="usb", is_error=True, classification="timeout"),
        ParsedEvent(raw="e2", level="INFO", module="network", is_error=False, classification="normal"),
        ParsedEvent(raw="e3", level="WARN", module="power", is_error=False, classification="normal"),
        ParsedEvent(raw="e4", level="ERROR", module="usb", is_error=True, classification="timeout"),
    ]
    result = ParseResult.from_events(events, log_id=42)

    assert result.log_id == 42
    assert result.status == "completed"
    assert result.event_count == 4
    assert result.error_count == 2
    assert result.warning_count == 1
    assert result.error_classifications == {"timeout": 2}
    assert len(result.events) == 4


def test_parse_result_empty_events():
    result = ParseResult.from_events([])
    assert result.event_count == 0
    assert result.error_count == 0
    assert result.source_type == "generic"


def test_parse_result_model_dump():
    events = [
        ParsedEvent(raw="error", level="ERROR", is_error=True, classification="timeout"),
    ]
    result = ParseResult.from_events(events, log_id=1)
    data = result.model_dump()
    assert data["event_count"] == 1
    assert data["error_count"] == 1
    assert len(data["events"]) == 1
    assert data["events"][0]["raw"] == "error"


# ------------------------------------------------------------------
# ParsedEventSchema
# ------------------------------------------------------------------


def test_parsed_event_schema():
    from datetime import datetime

    ts = datetime(2024, 10, 1, 10, 20, 30)
    schema = ParsedEventSchema(
        raw="test line",
        message="test message",
        level="ERROR",
        module="usb",
        source_type="kernel",
        is_error=True,
        classification="timeout",
        timestamp=ts,
        metadata={"uptime": 1.0},
    )
    d = schema.model_dump()
    assert d["level"] == "ERROR"
    assert d["is_error"] is True
    assert d["timestamp"] == ts


# ------------------------------------------------------------------
# RuleEngine with ParsedEvent
# ------------------------------------------------------------------


def test_rule_engine_with_parsed_events():
    engine = RuleEngine()
    events = [
        ParsedEvent(raw="e1", classification="timeout", module="usb"),
        ParsedEvent(raw="e2", classification="filesystem", module="ext4"),
    ]
    suggestions = engine.generate_suggestions(events)
    assert len(suggestions) == 2
    assert suggestions[0]["rule"] == "usb-timeout"
    assert suggestions[1]["rule"] == "filesystem-failure"


def test_rule_engine_with_dict_events():
    engine = RuleEngine()
    events = [
        {"classification": "timeout", "module": "usb"},
        {"classification": "panic", "module": "kernel"},
    ]
    suggestions = engine.generate_suggestions(events)
    assert len(suggestions) == 2
    assert suggestions[1]["rule"] == "kernel-panic"


def test_rule_engine_no_match():
    engine = RuleEngine()
    events = [ParsedEvent(raw="e1", classification="normal", module="system")]
    suggestions = engine.generate_suggestions(events)
    assert suggestions == []
