from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


LOG_LEVELS = {"ERROR", "WARN", "WARNING", "INFO", "DEBUG", "CRITICAL", "FATAL", "TRACE"}


@dataclass
class ParsedEvent:
    """Structured representation of a single log line after parsing."""

    raw: str
    message: str = ""
    level: str = "INFO"
    module: str = "system"
    source_type: str = "generic"
    is_error: bool = False
    classification: str = "unknown"
    timestamp: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        result = {
            "raw": self.raw,
            "level": self.level,
            "module": self.module,
            "message": self.message,
            "source_type": self.source_type,
            "is_error": self.is_error,
            "classification": self.classification,
        }
        if self.timestamp:
            result["timestamp"] = self.timestamp.isoformat()
        if self.metadata:
            result["metadata"] = self.metadata
        return result


class BaseParser(ABC):
    """Abstract base for all log format parsers.

    Each concrete parser handles a specific log format (e.g. Linux syslog,
    kernel dmesg, Android logcat) and produces a list of ParsedEvent objects.
    """

    # Override in subclass to describe what format this parser handles
    source_type: str = "generic"

    def __init__(self) -> None:
        self.error_keywords: List[str] = [
            "error", "failed", "exception", "crash",
            "timeout", "not responding", "panic", "oops",
            "segfault", "bus error", "corrupt", "bug",
            "null pointer", "dereference", "deadlock",
            "hung", "stuck", "overflow",
        ]

    @abstractmethod
    def can_parse(self, line: str) -> bool:
        """Return True if this parser can handle the given log line."""

    @abstractmethod
    def parse_line(self, line: str) -> ParsedEvent:
        """Parse a single log line into a structured event."""

    def parse_text(self, text: str) -> List[ParsedEvent]:
        """Parse multi-line text, skipping empty lines."""
        events: List[ParsedEvent] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(self.parse_line(stripped))
            except Exception:
                events.append(self._fallback_event(stripped))
        return events

    def _extract_level(self, line: str) -> str:
        import re

        match = re.search(
            r"\b(ERROR|CRITICAL|FATAL|WARN|WARNING|INFO|DEBUG|TRACE)\b",
            line,
            re.IGNORECASE,
        )
        return match.group(1).upper() if match else "INFO"

    def _is_error(self, line: str) -> bool:
        lowered = line.lower()
        return any(kw in lowered for kw in self.error_keywords)

    def _classify_error(self, line: str) -> str:
        lowered = line.lower()
        rules = [
            ("oom", "out of memory" in lowered or "oom" in lowered),
            ("timeout", "timeout" in lowered or "not responding" in lowered),
            ("filesystem", any(kw in lowered for kw in ("ext4", "filesystem", "inode", "xfs", "btrfs", "ntfs"))),
            ("memory", any(kw in lowered for kw in ("segfault", "segmentation fault", "page fault", "null pointer", "memory leak"))),
            ("panic", "panic" in lowered or "kernel panic" in lowered or "oops" in lowered),
            ("io_error", "i/o error" in lowered or "bad block" in lowered or "device error" in lowered),
            ("failure", "failed" in lowered),
        ]
        for classification, condition in rules:
            if condition:
                return classification
        return "unknown"

    @staticmethod
    def _fallback_event(line: str) -> ParsedEvent:
        return ParsedEvent(
            raw=line,
            message=line,
            level="INFO",
            module="system",
            source_type="generic",
            is_error=False,
            classification="unknown",
        )
