from __future__ import annotations

from typing import Any, Dict

from app.services.providers.base import BaseProvider


class MockProvider(BaseProvider):
    name = "mock"

    def generate_summary(self, log_content: str, events: list[Dict[str, Any]]) -> Dict[str, Any]:
        error_events = [event for event in events if event.get("is_error")]
        module_names = [str(event.get("module", "system")).lower() for event in error_events if event.get("module")]
        module_hint = module_names[0] if module_names else "device"
        log_content_lower = (log_content or "").lower()
        log_hint = "usb" if "usb" in log_content_lower else module_hint
        if error_events:
            summary = f"Detected {len(error_events)} error events in {log_hint}. The most likely issue is a device-side timeout or communication fault."
        else:
            summary = "No significant error patterns detected in the log."

        return {
            "model": self.name,
            "summary": summary,
            "confidence": 0.7,
            "root_cause": "Likely device-side communication fault or timeout." if error_events else "No clear root cause detected from the available log data.",
            "next_steps": ["Inspect the affected device interface and timing behavior.", "Verify cable, driver, and peripheral state."],
            "event_count": len(events),
            "error_count": len(error_events),
        }
