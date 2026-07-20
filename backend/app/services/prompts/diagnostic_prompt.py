"""Diagnostic prompt templates for LLM-based log analysis.

Prompts are versioned and managed separately from provider code
to allow independent iteration and A/B testing.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


class DiagnosticPrompt:
    """Build structured prompts for device log diagnostic analysis."""

    VERSION = "1.0"

    SYSTEM_PROMPT = (
        "You are an expert embedded systems and device diagnostics engineer. "
        "Your job is to analyze device logs, identify root causes, and provide "
        "actionable next steps for engineers.\n\n"
        "Rules:\n"
        "1. Base conclusions ONLY on evidence found in the log.\n"
        "2. Never fabricate errors or symptoms not present in the log.\n"
        "3. Provide confidence scores reflecting how certain you are.\n"
        "4. Give specific, actionable next steps (not generic advice).\n"
        "5. Output ONLY valid JSON — no markdown, no explanation outside JSON.\n"
    )

    OUTPUT_SCHEMA = {
        "summary": "A concise 1-3 sentence summary of what was found.",
        "confidence": "A float between 0.0 and 1.0 indicating diagnostic confidence.",
        "root_cause": "The most likely root cause based on log evidence.",
        "next_steps": "A list of 2-5 specific, actionable investigation steps.",
    }

    @classmethod
    def build(cls, log_content: str, events: List[Dict[str, Any]]) -> str:
        """Build the full user prompt for diagnostic analysis.

        Args:
            log_content: Raw log file content.
            events: Pre-parsed structured events from the parser engine.
        """
        # Build a focused event summary
        error_events = [e for e in events if e.get("is_error")]
        error_summary = cls._build_error_summary(error_events)

        return (
            f"{cls.SYSTEM_PROMPT}\n\n"
            f"--- LOG ANALYSIS TASK ---\n\n"
            f"PARSED EVENTS: {len(events)} total, {len(error_events)} errors\n\n"
            f"ERROR SUMMARY:\n{error_summary}\n\n"
            f"RAW LOG CONTENT:\n{log_content[:8000]}\n\n"
            f"---\n"
            f"Return a JSON object with these fields:\n"
            f"{json.dumps(cls.OUTPUT_SCHEMA, indent=2)}\n\n"
            f"Output ONLY the JSON object, nothing else."
        )

    @classmethod
    def _build_error_summary(cls, error_events: List[Dict[str, Any]]) -> str:
        if not error_events:
            return "No error events detected."

        # Group by classification
        grouped: Dict[str, List[str]] = {}
        for ev in error_events:
            cls_name = ev.get("classification", "unknown")
            module = ev.get("module", "system")
            grouped.setdefault(cls_name, []).append(module)

        lines = []
        for classification, modules in grouped.items():
            unique_modules = list(dict.fromkeys(modules))
            lines.append(
                f"  - {classification} ({len(modules)} occurrences, modules: {', '.join(unique_modules[:3])})"
            )
        return "\n".join(lines)
