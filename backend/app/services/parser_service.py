from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional


class LogParserService:
    """Parse common device and system log lines into structured events."""

    def __init__(self) -> None:
        self.error_keywords = ["error", "failed", "exception", "crash", "timeout", "not responding"]

    def parse_text(self, text: str) -> List[Dict[str, object]]:
        events: List[Dict[str, object]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            events.append(self._parse_line(line))
        return events

    def parse_file(self, path: str | Path) -> List[Dict[str, object]]:
        file_path = Path(path)
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        return self.parse_text(text)

    def _parse_line(self, line: str) -> Dict[str, object]:
        lowered = line.lower()
        source_type = self._detect_source_type(line)
        level = self._extract_level(line)
        module = self._extract_module(line)
        message = line
        is_error = any(keyword in lowered for keyword in self.error_keywords)
        classification = self._classify_error(line)

        return {
            "raw": line,
            "level": level,
            "module": module,
            "message": message,
            "source_type": source_type,
            "is_error": is_error,
            "classification": classification,
        }

    def _detect_source_type(self, line: str) -> str:
        if "kernel" in line.lower():
            return "kernel"
        if "usb" in line.lower():
            return "usb"
        return "generic"

    def _extract_level(self, line: str) -> str:
        match = re.search(r"\b(ERROR|WARN|WARNING|INFO|DEBUG)\b", line, re.IGNORECASE)
        return match.group(1).upper() if match else "INFO"

    def _extract_module(self, line: str) -> str:
        match = re.search(r"\b(ERROR|WARN|WARNING|INFO|DEBUG)\s+([a-zA-Z0-9_.-]+):", line, re.IGNORECASE)
        if match:
            return match.group(2).lower()

        match = re.search(r"^([a-zA-Z0-9_.-]+):", line)
        if match:
            return match.group(1).lower()

        if "usb" in line.lower():
            return "usb"
        return "system"

    def _classify_error(self, line: str) -> str:
        lowered = line.lower()
        if "timeout" in lowered or "not responding" in lowered:
            return "timeout"
        if "ext4" in lowered or "filesystem" in lowered or "inode" in lowered:
            return "filesystem"
        if "failed" in lowered:
            return "failure"
        return "unknown"
