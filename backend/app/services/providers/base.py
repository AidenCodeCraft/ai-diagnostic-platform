from __future__ import annotations

from typing import Any, Dict


class BaseProvider:
    name = "base"

    def generate_summary(self, log_content: str, events: list[Dict[str, Any]]) -> Dict[str, Any]:
        raise NotImplementedError
