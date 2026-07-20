from __future__ import annotations

import re
from typing import List, Optional

from app.services.parser.base import BaseParser, ParsedEvent


class GenericParser(BaseParser):
    """Fallback parser that handles any log line without a specific format.

    Extracts level, module, and classification using regex heuristics.
    Works as the default parser when no specialized parser matches.
    """

    source_type = "generic"

    def can_parse(self, line: str) -> bool:
        # Generic parser accepts everything as a last resort
        return True

    def parse_line(self, line: str) -> ParsedEvent:
        level = self._extract_level(line)
        module = self._extract_module(line)
        is_error = self._is_error(line)
        classification = self._classify_error(line) if is_error else "normal"

        return ParsedEvent(
            raw=line,
            message=line,
            level=level,
            module=module,
            source_type=self.source_type,
            is_error=is_error,
            classification=classification,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_module(line: str) -> str:
        """Extract module name from various log patterns."""
        # Pattern: "LEVEL module: message"
        m = re.search(
            r"\b(ERROR|WARN|WARNING|INFO|DEBUG|CRITICAL|FATAL|TRACE)\s+([a-zA-Z0-9_.-]+)\s*[:\[(]",
            line,
            re.IGNORECASE,
        )
        if m:
            return m.group(2).lower()

        # Pattern: "module: rest of line"
        m = re.match(r"^([a-zA-Z0-9_.-]+)\s*:\s+", line)
        if m:
            return m.group(1).lower()

        # Known module heuristics
        lowered = line.lower()
        modules = [
            "usb", "pci", "bluetooth", "net", "wifi", "sensor",
            "power", "audio", "display", "camera", "gps", "nfc",
            "thermal", "battery", "modem", "storage", "memory",
        ]
        for mod in modules:
            if mod in lowered:
                return mod

        return "system"
