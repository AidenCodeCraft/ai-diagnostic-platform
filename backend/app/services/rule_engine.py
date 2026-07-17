from __future__ import annotations

from typing import Dict, List


class RuleEngine:
    """Simple rule-based diagnostic suggestions for parsed events."""

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
        ]

    def generate_suggestions(self, events: List[Dict[str, object]]) -> List[Dict[str, object]]:
        suggestions: List[Dict[str, object]] = []
        for event in events:
            classification = str(event.get("classification", "")).lower()
            for rule in self.rules:
                if rule["match"] in classification:
                    suggestions.append({
                        "rule": rule["name"],
                        "message": rule["suggestion"],
                        "module": event.get("module"),
                    })
                    break
        return suggestions
