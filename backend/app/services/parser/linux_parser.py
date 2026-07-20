from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from app.services.parser.base import BaseParser, ParsedEvent


# Linux syslog / rsyslog typical format:
#   Oct  1 10:20:30 hostname process[PID]: message
#   or
#   2024-10-01T10:20:30.123Z hostname process[PID]: message
_SYSLOG_PATTERN = re.compile(
    r"^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"  # traditional: Oct  1 10:20:30
    r"(\S+)\s+"                                      # hostname
    r"(\S+?)(?:\[(\d+)\])?\s*:\s+"                   # process[PID]:
    r"(.*)",                                          # message
)

_ISO_SYSLOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)\s+"
    r"(\S+)\s+"
    r"(\S+?)(?:\[(\d+)\])?\s*:\s+"
    r"(.*)",
)

_KERNEL_SYSLOG_PATTERN = re.compile(
    r"^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(\S+)\s+"
    r"kernel\s*:\s*"
    r"(.*)",
)


class LinuxSyslogParser(BaseParser):
    """Parser for standard Linux syslog/rsyslog lines."""

    source_type = "linux_syslog"

    def can_parse(self, line: str) -> bool:
        return bool(_SYSLOG_PATTERN.match(line) or _ISO_SYSLOG_PATTERN.match(line))

    def parse_line(self, line: str) -> ParsedEvent:
        timestamp = self._extract_timestamp(line)
        hostname: str = "localhost"
        process: str = "unknown"
        message: str = line

        # Try traditional syslog format first
        m = _SYSLOG_PATTERN.match(line)
        if m:
            if not timestamp:
                timestamp = self._parse_traditional_timestamp(m.group(1))
            hostname = m.group(2)
            process = m.group(3)
            message = m.group(5)
        else:
            # Try ISO format
            m2 = _ISO_SYSLOG_PATTERN.match(line)
            if m2:
                if not timestamp:
                    timestamp = self._parse_iso_timestamp(m2.group(1))
                hostname = m2.group(2)
                process = m2.group(3)
                message = m2.group(5)

        level = self._extract_level(line)
        is_error = self._is_error(line)
        classification = self._classify_error(line) if is_error else "normal"

        return ParsedEvent(
            raw=line,
            message=message,
            level=level,
            module=process,
            source_type=self.source_type,
            is_error=is_error,
            classification=classification,
            timestamp=timestamp,
        )

    @staticmethod
    def _parse_traditional_timestamp(ts_str: str) -> Optional[datetime]:
        """Parse 'Oct  1 10:20:30' style timestamp (without year)."""
        try:
            return datetime.strptime(ts_str, "%b %d %H:%M:%S")
        except ValueError:
            return None

    @staticmethod
    def _parse_iso_timestamp(ts_str: str) -> Optional[datetime]:
        """Parse ISO 8601 timestamps."""
        ts_str = ts_str.replace("T", " ").rstrip("Z")
        for fmt in (
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                return datetime.strptime(ts_str, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _extract_timestamp(line: str) -> Optional[datetime]:
        """Try kernel dmesg timestamp: [  123.456789]"""
        m = re.match(r"\[\s*(\d+\.\d+)\]\s+", line)
        if m:
            return None  # kernel uptime, not real timestamp
        return LinuxSyslogParser._parse_iso_timestamp(line[:26].strip())
