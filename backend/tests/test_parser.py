from pathlib import Path

from app.services.parser_service import LogParserService


def test_parse_text_extracts_linux_log_details():
    parser = LogParserService()

    events = parser.parse_text(
        "2024-10-01 10:20:30 ERROR usb: device timeout while reading descriptor"
    )

    assert len(events) == 1
    assert events[0]["level"] == "ERROR"
    assert events[0]["module"] == "usb"
    assert events[0]["is_error"] is True
    assert events[0]["classification"] == "timeout"


def test_parse_file_detects_kernel_errors(tmp_path: Path):
    parser = LogParserService()
    log_file = tmp_path / "kernel.log"
    log_file.write_text(
        "kernel: [ 123.456789] usb 1-1: device not responding\n"
        "kernel: [ 123.500000] ext4 error: failed to write inode\n",
        encoding="utf-8",
    )

    events = parser.parse_file(log_file)

    assert len(events) == 2
    assert events[0]["source_type"] == "kernel"
    assert events[0]["classification"] == "timeout"
    assert events[1]["is_error"] is True
    assert events[1]["classification"] == "filesystem"
