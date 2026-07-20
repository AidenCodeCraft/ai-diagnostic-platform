"""Report generation service — creates diagnostic reports from analysis results."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.analysis import Analysis
from app.models.log import Log
from app.models.report import Report


class ReportService:
    """Service for generating, listing, and exporting diagnostic reports."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

    def generate_report(self, log_id: int) -> Dict[str, Any]:
        """Generate a diagnostic report from analysis results."""
        log = self._get_log(log_id)
        analysis = self._get_analysis(log_id)

        summary = analysis.summary or "No summary available."
        root_cause = analysis.root_cause or "Root cause not available."
        confidence = analysis.confidence
        next_steps = self._parse_next_steps(analysis.next_steps)
        model = analysis.model or "mock"

        title = f"Diagnostic Report for {log.filename}"
        report_data = {
            "title": title,
            "summary": summary,
            "root_cause": root_cause,
            "confidence": confidence,
            "next_steps": next_steps,
            "model": model,
            "log_filename": log.filename,
            "log_id": log.id,
            "device": log.device,
            "version": log.version,
        }

        # Upsert
        report = self.db.query(Report).filter(
            Report.analysis_id == analysis.id
        ).first()
        if report is None:
            report = Report(
                log_id=log.id,
                analysis_id=analysis.id,
                title=title,
                content=json.dumps(report_data),
                format="json",
            )
            self.db.add(report)
        else:
            report.content = json.dumps(report_data)
            report.title = title

        self.db.commit()
        self.db.refresh(report)

        return {
            "report_id": report.id,
            "analysis_id": analysis.id,
            "log_id": log.id,
            "title": title,
            "summary": summary,
            "root_cause": root_cause,
            "confidence": confidence,
            "next_steps": next_steps,
            "model": model,
            "format": report.format,
            "created_at": report.created_at.isoformat() if report.created_at else None,
        }

    def export_markdown(self, report_id: int) -> str:
        """Export a report as Markdown text."""
        report = self.get_report(report_id)
        content = self._decode_content(report.content)
        return self._to_markdown(content)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_report(self, report_id: int) -> Report:
        report = self.db.query(Report).filter(Report.id == report_id).first()
        if not report:
            raise ValueError("report not found")
        return report

    def get_report_detail(self, report_id: int) -> Dict[str, Any]:
        report = self.get_report(report_id)
        content = self._decode_content(report.content)

        return {
            "id": report.id,
            "log_id": report.log_id,
            "analysis_id": report.analysis_id,
            "title": report.title,
            "format": report.format,
            "summary": content.get("summary", ""),
            "root_cause": content.get("root_cause", ""),
            "confidence": content.get("confidence"),
            "next_steps": self._parse_next_steps(content.get("next_steps")),
            "model": content.get("model", "mock"),
            "created_at": report.created_at.isoformat() if report.created_at else None,
        }

    def list_reports(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        query = self.db.query(Report)
        total = query.count()
        items = (
            query.order_by(Report.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        results = []
        for report in items:
            content = self._decode_content(report.content)
            results.append({
                "id": report.id,
                "log_id": report.log_id,
                "analysis_id": report.analysis_id,
                "title": report.title,
                "format": report.format,
                "summary": content.get("summary", ""),
                "root_cause": content.get("root_cause", ""),
                "confidence": content.get("confidence"),
                "next_steps": self._parse_next_steps(content.get("next_steps")),
                "model": content.get("model", "mock"),
                "created_at": report.created_at.isoformat() if report.created_at else None,
            })

        return {
            "items": results,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_report(self, report_id: int) -> None:
        report = self.get_report(report_id)
        self.db.delete(report)
        self.db.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_log(self, log_id: int) -> Log:
        log = self.db.query(Log).filter(Log.id == log_id).first()
        if not log:
            raise ValueError("log not found")
        return log

    def _get_analysis(self, log_id: int) -> Analysis:
        analysis = self.db.query(Analysis).filter(
            Analysis.log_id == log_id
        ).first()
        if not analysis:
            raise ValueError("analysis not found — run analysis first")
        return analysis

    @staticmethod
    def _decode_content(content: str | None) -> Dict[str, Any]:
        if not content:
            return {}
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw": content}

    @staticmethod
    def _parse_next_steps(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except json.JSONDecodeError:
                return [value]
        return []

    @staticmethod
    def _to_markdown(data: Dict[str, Any]) -> str:
        title = data.get("title", "Diagnostic Report")
        summary = data.get("summary", "N/A")
        root_cause = data.get("root_cause", "N/A")
        confidence = data.get("confidence", "N/A")
        next_steps = data.get("next_steps", [])
        model = data.get("model", "unknown")
        device = data.get("device", "unknown")

        md = f"# {title}\n\n"
        md += f"**Device**: {device}\n"
        md += f"**Model**: {model}\n"
        md += f"**Confidence**: {confidence}\n\n"
        md += f"## Summary\n\n{summary}\n\n"
        md += f"## Root Cause\n\n{root_cause}\n\n"
        md += "## Recommended Next Steps\n\n"
        for i, step in enumerate(next_steps, 1):
            md += f"{i}. {step}\n"
        md += "\n---\n*Generated by AI Diagnostic Platform*\n"
        return md
