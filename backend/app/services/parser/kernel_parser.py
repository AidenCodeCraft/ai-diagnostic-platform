from __future__ import annotations

import re
from typing import Optional

from app.services.parser.base import BaseParser, ParsedEvent


# Kernel dmesg format: [  SECONDS.MICROSECONDS] message
_DMESG_PATTERN = re.compile(r"\[\s*(\d+\.\d+)\]\s+(.*)")

# Common kernel subsystems for module extraction
_KERNEL_MODULES = [
    "usb", "pci", "bluetooth", "net", "wifi", "block",
    "scsi", "ata", "i2c", "spi", "gpio", "mmc", "sdhci",
    "drm", "ext4", "xfs", "btrfs", "vfs", "nfs",
    "cpu", "memory", "oom", "swap",
]
_MODULE_PATTERN = re.compile(
    r"\b(" + "|".join(_KERNEL_MODULES) + r")\b", re.IGNORECASE
)


class KernelLogParser(BaseParser):
    """Parser for Linux kernel ring buffer (dmesg) output."""

    source_type = "kernel"

    def can_parse(self, line: str) -> bool:
        return bool(_DMESG_PATTERN.match(line)) or self._looks_like_kernel(line)

    def parse_line(self, line: str) -> ParsedEvent:
        uptime: Optional[float] = None
        message: str = line

        m = _DMESG_PATTERN.match(line)
        if m:
            uptime = float(m.group(1))
            message = m.group(2).strip()

        level = self._extract_kernel_level(line)
        module = self._extract_kernel_module(line)
        is_error = self._is_error(line)
        classification = self._classify_error(line) if is_error else "normal"

        return ParsedEvent(
            raw=line,
            message=message,
            level=level,
            module=module,
            source_type=self.source_type,
            is_error=is_error,
            classification=classification,
            metadata={"uptime_seconds": uptime} if uptime is not None else {},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_kernel_level(line: str) -> str:
        """Kernel uses <N> prefix (0=EMERG .. 7=DEBUG)."""
        m = re.match(r"<(\d)>", line)
        if m:
            level_map = {
                "0": "EMERG",
                "1": "ALERT",
                "2": "CRITICAL",
                "3": "ERROR",
                "4": "WARN",
                "5": "NOTICE",
                "6": "INFO",
                "7": "DEBUG",
            }
            return level_map.get(m.group(1), "INFO")

        # Fallback to standard level detection via regex
        match = re.search(
            r"\b(EMERG|ALERT|CRITICAL|ERROR|FATAL|WARN|WARNING|INFO|DEBUG|TRACE)\b",
            line,
            re.IGNORECASE,
        )
        return match.group(1).upper() if match else "INFO"

    @staticmethod
    def _extract_kernel_module(line: str) -> str:
        lowered = line.lower()
        m = _MODULE_PATTERN.search(lowered)
        if m:
            return m.group(1).lower()

        # Detect from known patterns
        if "kernel" in lowered or "dmesg" in lowered:
            return "kernel"
        if "systemd" in lowered:
            return "systemd"
        return "kernel"

    @staticmethod
    def _looks_like_kernel(line: str) -> bool:
        """Heuristic: detect kernel log lines without standard dmesg prefix."""
        lowered = line.lower()
        # Common kernel log patterns
        prefixes = ["kernel:", "kern ", "kern.", "<0>", "<1>", "<2>", "<3>", "<4>", "<5>", "<6>", "<7>"]
        for pfx in prefixes:
            if lowered.startswith(pfx):
                return True

        indicators = [
            "dmesg:", "trap", "interrupt", "hrtimer", "rcu_sched",
            "sched:", "workqueue", "debugfs", "sysfs", "procfs",
            "ext4-fs", "xfs:", "btrfs:", "vfs:", "block:",
            "usb ", "pci ", "bluetooth:", "net:", "wifi:",
            "bug:", "oops:", "panic:", "null pointer",
            "unable to handle", "not responding", "timeout",
            "mmc", "sdhci", "i2c", "spi", "gpio",
        ]
        return any(ind in lowered for ind in indicators)
