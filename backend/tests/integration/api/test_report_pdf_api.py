"""真实 PDF 导出 API 回归测试（默认跳过）。

缺口背景：`GET /api/v1/reports/{report_id}/pdf` 此前只有 service 级单元测试
（tests/unit/services/test_report_pdf.py），缺少 API 级回归测试；且部署镜像
若未安装 reportlab，该路由会返回 501。本模块补齐 API 层断言，默认收集即 skip，
避免在未安装 reportlab 的环境污染全量 pytest。

启用方式（本地/CI 显式开启）：

    RUN_REAL_PDF_API=1 pytest tests/integration/api/test_report_pdf_api.py -v

测试使用 TestClient + 内存 SQLite（不依赖外部服务/真实部署），断言：
    HTTP 200、Content-Type: application/pdf、%PDF 魔数、大小 >1KB、
    页数 >= 1、Content-Disposition 正确、字体资源引用 STSong-Light（中文 CID 生效）。
pypdf 为可选开发依赖：未安装时页数/字体结构退化为原始字节校验。
"""

from __future__ import annotations

import importlib
import importlib.util
import io
import os
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import session as session_module

RUN_REAL_PDF_API = os.getenv("RUN_REAL_PDF_API") == "1"
HAS_REPORTLAB = importlib.util.find_spec("reportlab") is not None

pytestmark = [
    pytest.mark.skipif(
        not RUN_REAL_PDF_API,
        reason="默认跳过：设置 RUN_REAL_PDF_API=1 才运行真实 PDF API 测试",
    ),
    pytest.mark.skipif(
        not HAS_REPORTLAB,
        reason="reportlab 未安装，PDF 导出不可用（预期 501）",
    ),
]

SYSLOG_BODY = (
    b"Nov 12 03:12:01 D3C usbhub: ERROR: port 2 over-current condition detected\n"
    b"Nov 12 03:12:05 D3C kernel: [ 123.460112] xhci_hcd: ERROR: host controller not responding\n"
    b"Nov 12 03:12:21 D3C diagnostic-agent: ERROR: device heartbeat lost, usb bus unstable\n"
)


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """与 tests/integration/api/test_report_generation.py 一致的内存库 TestClient。"""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))

    import app.core.config as config_module
    import app.main as main_module

    config_module.settings.DATABASE_URL = "sqlite:///:memory:"
    config_module.settings.UPLOAD_DIR = str(tmp_path / "uploads")

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_module.engine = engine
    session_module.SessionLocal = sessionmaker(
        bind=engine, autocommit=False, autoflush=False
    )
    session_module.init_db()

    importlib.reload(main_module)

    with TestClient(main_module.app) as test_client:
        yield test_client


def _prepare_report(client: TestClient) -> int:
    """上传日志 → 解析 → mock 分析 → 生成报告，返回 report_id。"""
    upload = client.post(
        "/api/v1/logs/upload",
        files={"file": ("pdf_e2e.log", SYSLOG_BODY, "text/plain")},
        data={"device": "D3C", "version": "v2.3.1"},
    )
    assert upload.status_code == 200, upload.text
    log_id = upload.json()["id"]

    parse = client.post(f"/api/v1/logs/{log_id}/parse")
    assert parse.status_code == 200, parse.text
    assert parse.json().get("event_count", 0) > 0

    analysis = client.post(f"/api/v1/analyses/run?log_id={log_id}&model=mock")
    assert analysis.status_code == 200, analysis.text
    assert analysis.json().get("status") == "completed"

    report = client.post(f"/api/v1/reports/{log_id}")
    assert report.status_code == 200, report.text
    report_id = report.json()["report_id"]
    assert report_id
    return int(report_id)


def _page_count(pdf_bytes: bytes) -> int:
    """优先用 pypdf 解析页数；未安装时退回原始字节统计（够用于 >=1 判定）。"""
    if importlib.util.find_spec("pypdf") is not None:
        from pypdf import PdfReader

        return len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    return len(re.findall(rb"/Type\s*/Page(?![s])", pdf_bytes))


def _font_base_fonts(pdf_bytes: bytes) -> list[str]:
    """返回 PDF 中引用的 BaseFont 名称（需 pypdf；未安装时返回空列表）。"""
    if importlib.util.find_spec("pypdf") is None:
        return []
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    names: set[str] = set()
    for page in reader.pages:
        resources = page.get("/Resources")
        fonts = resources.get("/Font") if resources else None
        if not fonts:
            continue
        for _key, reference in fonts.items():
            font = reference.get_object()
            base_font = font.get("/BaseFont")
            if base_font:
                names.add(str(base_font))
    return sorted(names)


def test_pdf_export_api_returns_valid_pdf(client):
    """完整链路后 GET /reports/{id}/pdf 返回合法 PDF（reportlab 真实渲染）。"""
    report_id = _prepare_report(client)

    response = client.get(f"/api/v1/reports/{report_id}/pdf")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="report_{report_id}.pdf"'
    )

    pdf_bytes = response.content
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1024

    pages = _page_count(pdf_bytes)
    assert pages >= 1, f"PDF 页数异常: {pages}"

    # reportlab 注册的 UnicodeCIDFont 会以 /STSong-Light 出现在字体资源/原始字节中
    assert b"STSong" in pdf_bytes, "PDF 中未出现 STSong 字体引用，中文 CID 字体未生效"
    base_fonts = _font_base_fonts(pdf_bytes)
    if base_fonts:
        assert any("STSong" in name for name in base_fonts), base_fonts


def test_pdf_export_api_unknown_report_returns_404(client):
    """不存在的报告导出 PDF 返回 404（而非 500/501）。"""
    response = client.get("/api/v1/reports/99999999/pdf")
    assert response.status_code == 404, response.text
