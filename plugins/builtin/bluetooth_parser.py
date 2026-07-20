"""Built-in Bluetooth log parser plugin.

Demonstrates the Parser plugin pattern for Bluetooth/HCI logs.
"""

from __future__ import annotations

import re
from typing import List

from plugins.sdk.plugin_base import PluginBase
from plugins.sdk.manifest import PluginType


class BluetoothLogParser(PluginBase):
    """Specialized parser for Bluetooth / HCI subsystem logs."""

    plugin_type = PluginType.PARSER

    _BT_ERRORS = [
        (r"Bluetooth: hci(\d+) command (\w+) timeout", "hci_timeout"),
        (r"Bluetooth: (Connection|Link) (timeout|failed|lost)", "connection_error"),
        (r"hci(\d+): (firmware|fw) (error|crash|load failed)", "firmware_error"),
        (r"Bluetooth: (SCO|ACL) link (error|disconnect|timeout)", "link_error"),
        (r"bt_(usb|hci|uart|sdio)_(error|fail|timeout)", "transport_error"),
    ]

    def on_initialize(self, config=None) -> None:
        super().on_initialize(config)
        self._compiled = [(re.compile(pat, re.IGNORECASE), cls) for pat, cls in self._BT_ERRORS]

    def parse(self, line: str) -> dict | None:
        for pattern, classification in self._compiled:
            m = pattern.search(line)
            if m:
                return {
                    "module": "bluetooth",
                    "classification": classification,
                    "is_error": True,
                    "details": m.group(0),
                }
        return None

    def parse_text(self, text: str) -> List[dict]:
        events = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            event = self.parse(line)
            if event:
                events.append(event)
        return events
