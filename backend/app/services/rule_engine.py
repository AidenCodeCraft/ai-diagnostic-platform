from __future__ import annotations

from typing import Dict, List, Union

from app.services.parser.base import ParsedEvent


class RuleEngine:
    """Simple rule-based diagnostic suggestions for parsed events.

    Accepts either ParsedEvent objects or plain dicts for backward compatibility.
    """

    def __init__(self) -> None:
        self.rules = [
            {
                "name": "usb-timeout",
                "match": "timeout",
                "suggestion": "Check USB cable, connector seating, and power rails before continuing.",
            },
            {
                "name": "filesystem-failure",
                "match": "filesystem",
                "suggestion": "Inspect storage mount state and file system logs for corruption or I/O errors.",
            },
            {
                "name": "oom-killer",
                "match": "oom",
                "suggestion": "System ran out of memory. Check process memory usage, page cache, and consider adding swap or increasing RAM.",
            },
            {
                "name": "kernel-panic",
                "match": "panic",
                "suggestion": "Kernel panic detected. Capture full stack trace and check recent driver or kernel module changes.",
            },
            {
                "name": "memory-corruption",
                "match": "memory",
                "suggestion": "Possible memory corruption. Run memtest, check for buffer overflows, and review recent memory allocation changes.",
            },
        ]

    def generate_suggestions(
        self,
        events: List[Union[ParsedEvent, Dict[str, object]]],
    ) -> List[Dict[str, object]]:
        suggestions: List[Dict[str, object]] = []
        for event in events:
            classification = self._get_classification(event).lower()
            module = self._get_module(event)
            for rule in self.rules:
                if rule["match"] in classification:
                    suggestions.append({
                        "rule": rule["name"],
                        "message": rule["suggestion"],
                        "module": module or "system",
                    })
                    break
        return suggestions

    @staticmethod
    def _get_classification(event: Union[ParsedEvent, Dict[str, object]]) -> str:
        if isinstance(event, ParsedEvent):
            return event.classification or ""
        return str(event.get("classification", ""))

    @staticmethod
    def _get_module(event: Union[ParsedEvent, Dict[str, object]]) -> object:
        if isinstance(event, ParsedEvent):
            return event.module
        return event.get("module")
