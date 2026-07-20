"""Built-in tools for the diagnostic Agent."""

from __future__ import annotations

from typing import Any

from app.agents.core.tool import Tool, ToolRegistry, ToolResult
from app.services.llm_service import LLMService
from app.services.parser_service import LogParserService
from app.services.report_service import ReportService
from app.services.rule_engine import RuleEngine


class ParseLogTool(Tool):
    name = "parse_log"
    description = "Parse a log file into structured events. Requires log_file_path."

    def execute(self, **kwargs: Any) -> ToolResult:
        file_path = kwargs.get("log_file_path", "")
        if not file_path:
            return ToolResult(success=False, error="log_file_path is required")

        try:
            events = LogParserService().parse_file(file_path)
            return ToolResult(
                success=True,
                data={"events": events, "count": len(events)},
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


class RuleCheckTool(Tool):
    name = "rule_check"
    description = "Run rule engine against parsed events. Requires parse_log_result."

    def __init__(self) -> None:
        super().__init__()
        self.engine = RuleEngine()

    def execute(self, **kwargs: Any) -> ToolResult:
        parse_result = kwargs.get("parse_log_result", {})
        events = parse_result.get("events", [])

        if not events:
            return ToolResult(
                success=True,
                data={"suggestions": [], "count": 0},
            )

        suggestions = self.engine.generate_suggestions(events)
        return ToolResult(
            success=True,
            data={"suggestions": suggestions, "count": len(suggestions)},
        )


class LLMAnalyzeTool(Tool):
    name = "llm_analyze"
    description = "Send parsed events to LLM for diagnostic analysis. Requires parse_log_result."

    def execute(self, **kwargs: Any) -> ToolResult:
        log_content = kwargs.get("log_content", "")
        parse_result = kwargs.get("parse_log_result", {})
        events = parse_result.get("events", [])

        try:
            result = LLMService().generate_summary(log_content, events)
            return ToolResult(success=True, data=result)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


class GenerateReportTool(Tool):
    name = "generate_report"
    description = "Generate a diagnostic report. Requires db_session, log_id, and llm_analyze_result."

    def execute(self, **kwargs: Any) -> ToolResult:
        db = kwargs.get("db_session")
        log_id = kwargs.get("log_id")
        llm_result = kwargs.get("llm_analyze_result", {})

        if not db or not log_id:
            return ToolResult(success=False, error="db_session and log_id are required")

        try:
            report = ReportService(db).generate_report(log_id)
            return ToolResult(success=True, data=report)
        except ValueError:
            summary = llm_result.get("summary", "No analysis available.")
            root_cause = llm_result.get("root_cause", "Unknown.")
            return ToolResult(
                success=True,
                data={
                    "summary": summary,
                    "root_cause": root_cause,
                    "next_steps": llm_result.get("next_steps", []),
                    "model": llm_result.get("model", "unknown"),
                },
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------


def create_default_registry() -> ToolRegistry:
    """Create a ToolRegistry pre-populated with built-in diagnostic tools."""
    registry = ToolRegistry()
    registry.register(ParseLogTool())
    registry.register(RuleCheckTool())
    registry.register(LLMAnalyzeTool())
    registry.register(GenerateReportTool())
    return registry
