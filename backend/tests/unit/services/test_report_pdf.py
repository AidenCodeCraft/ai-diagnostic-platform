"""报告 PDF 导出（reportlab 可选依赖）。"""

import importlib.util

import pytest

from app.models import Report
from app.services.diagnostics.report_service import (
    ReportExportUnavailable,
    ReportService,
)

HAS_REPORTLAB = importlib.util.find_spec("reportlab") is not None


def _make_report(db_session) -> Report:
    report = Report(
        log_id=None,
        analysis_id=None,
        title="测试报告",
        content=(
            '{"title": "测试报告", "summary": "摘要内容", "root_cause": "根因",'
            ' "confidence": 0.8, "next_steps": ["检查线缆"], "device": "D3C"}'
        ),
        format="json",
    )
    db_session.add(report)
    db_session.commit()
    db_session.refresh(report)
    return report


@pytest.mark.skipif(HAS_REPORTLAB, reason="reportlab 已安装，改测真实导出")
def test_pdf_export_requires_reportlab(db_session):
    report = _make_report(db_session)
    with pytest.raises(ReportExportUnavailable):
        ReportService(db_session).export_pdf(int(report.id))


@pytest.mark.skipif(not HAS_REPORTLAB, reason="reportlab 未安装")
def test_pdf_export_returns_pdf_bytes(db_session):
    report = _make_report(db_session)
    payload = ReportService(db_session).export_pdf(int(report.id))
    assert payload.startswith(b"%PDF")
    assert len(payload) > 100
