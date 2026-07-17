from __future__ import annotations


class DiagnosticPrompt:
    @staticmethod
    def build(log_content: str, events: list[dict]) -> str:
        return (
            "You are an expert device diagnostics assistant. "
            "Analyze the following log and return a JSON object with fields: "
            "summary, confidence, root_cause, next_steps. "
            f"Log content: {log_content}"
        )
