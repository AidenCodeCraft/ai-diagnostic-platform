"""Simple sequential planner for diagnostic workflow."""

from __future__ import annotations

from typing import Any, List


class SimplePlanner:
    """Generates a fixed diagnostic workflow plan.

    Plan: parse_log → rule_check → llm_analyze → generate_report
    """

    DEFAULT_PLAN = [
        "parse_log",
        "rule_check",
        "llm_analyze",
        "generate_report",
    ]

    def build_plan(self, log_id: int, **context: Any) -> List[str]:
        """Return the ordered list of tool names to execute."""
        return list(self.DEFAULT_PLAN)
