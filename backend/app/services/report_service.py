from __future__ import annotations

import json
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.analysis import Analysis
from app.models.log import Log
from app.models.report import Report


class ReportService:
    def __init__(self, db: Session):
        self.db = db

    def _decode_content(self, content: str | None) -> Dict[str, Any]:
        if not content:
            return {}
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"content": content}

    def list_reports(self) -> List[Dict[str, Any]]:
        reports = self.db.query(Report).all()
        result = []
        for report in reports:
            payload = self._decode_content(report.content)
            result.append(
                {
                    "report_id": report.id,
                    "analysis_id": report.analysis_id,
                    "summary": payload.get("summary", ""),
                    "root_cause": payload.get("root_cause", ""),
                    "next_steps": payload.get("next_steps", []),
                    "model": payload.get("model", "mock"),
                }
            )
        return result

    def get_report(self, report_id: int) -> Dict[str, Any]:
        report = self.db.query(Report).filter(Report.id == report_id).first()
        if not report:
            raise ValueError("report not found")
        payload = self._decode_content(report.content)
        payload.setdefault("report_id", report.id)
        payload.setdefault("analysis_id", report.analysis_id)
        return payload

    def generate_report(self, log_id: int) -> Dict[str, Any]:
        log = self.db.query(Log).filter(Log.id == log_id).first()
        if not log:
            raise ValueError("log not found")

        analysis = self.db.query(Analysis).filter(Analysis.log_id == log_id).first()
        if not analysis:
            raise ValueError("analysis not found")

        summary = analysis.summary or "No summary available"
        root_cause = analysis.root_cause or "Root cause not available"
        next_steps = []
        if analysis.next_steps:
            try:
                next_steps = json.loads(analysis.next_steps)
            except json.JSONDecodeError:
                next_steps = [analysis.next_steps]

        report_content = {
            "title": f"Diagnostic Report for {log.filename}",
            "summary": summary,
            "root_cause": root_cause,
            "next_steps": next_steps,
            "model": analysis.model or "mock",
        }

        report = self.db.query(Report).filter(Report.analysis_id == analysis.id).first()
        if report is None:
            report = Report(analysis_id=analysis.id, content=json.dumps(report_content))
            self.db.add(report)
        else:
            report.content = json.dumps(report_content)

        self.db.commit()
        self.db.refresh(report)

        return {
            "report_id": report.id,
            "analysis_id": analysis.id,
            "summary": summary,
            "root_cause": root_cause,
            "next_steps": next_steps,
            "model": analysis.model or "mock",
        }
