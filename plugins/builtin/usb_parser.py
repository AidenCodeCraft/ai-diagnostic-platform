"""Built-in USB log parser plugin.

Demonstrates the Parser plugin pattern: specialized log parsing
for USB subsystem logs.
"""

from __future__ import annotations

import re
from typing import List

from plugins.sdk.plugin_base import PluginBase
from plugins.sdk.manifest import PluginManifest, PluginType


class USBLogParser(PluginBase):
    """Specialized parser for USB subsystem logs."""

    plugin_type = PluginType.PARSER

    # Common USB error patterns
    _USB_ERRORS = [
        (r"device descriptor read/(\d+), error (-?\d+)", "descriptor_error"),
        (r"device not accepting address (\d+)", "address_error"),
        (r"unable to enumerate USB device", "enumeration_failure"),
        (r"USB disconnect, device number (\d+)", "disconnect"),
        (r"over-current condition", "over_current"),
        (r"reset (high-speed|full-speed|low-speed) USB", "reset"),
        (r"cannot enable. Maybe the USB cable is bad", "cable_fault"),
        (r"device not responding", "timeout"),
    ]

    def on_initialize(self, config=None) -> None:
        super().on_initialize(config)
        self._compiled = [(re.compile(pat, re.IGNORECASE), cls) for pat, cls in self._USB_ERRORS]

    def parse(self, line: str) -> dict | None:
        """Parse a single log line. Returns event dict or None if no match."""
        for pattern, classification in self._compiled:
            m = pattern.search(line)
            if m:
                return {
                    "module": "usb",
                    "classification": classification,
                    "is_error": True,
                    "details": m.group(0),
                    "groups": m.groups(),
                }
        return None

    def parse_text(self, text: str) -> List[dict]:
        """Parse multi-line text, extracting USB errors."""
        events = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            event = self.parse(line)
            if event:
                events.append(event)
        return events
