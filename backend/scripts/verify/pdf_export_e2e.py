#!/usr/bin/env python
"""PDF 报告导出端到端真实服务验证脚本（reportlab 部署验证）。

链路（全部走真实 HTTP，默认 http://localhost:8000）：
    POST /api/v1/logs/upload               上传 syslog 文本
    POST /api/v1/logs/{id}/parse           解析日志（可选，分析管线也会解析）
    POST /api/v1/analyses/run?log_id=N     以 mock LLM 跑完整诊断分析
    POST /api/v1/reports/{log_id}          由分析结果生成报告
    GET  /api/v1/reports/{report_id}/pdf   导出 PDF（本脚本核心校验对象）

前置条件：后端服务已启动，且镜像内已安装 reportlab（否则该路由可能 404/501）。
镜像验证命令（宿主机）：
    docker run --rm --entrypoint python deploy-backend:latest -c "import reportlab; print(reportlab.Version)"

用法（在 backend 目录下执行，使用项目 venv）：
    .venv\\Scripts\\python.exe scripts\\verify\\pdf_export_e2e.py

可选环境变量：
    API_BASE_URL   服务地址，默认 http://localhost:8000
    E2E_TIMEOUT    单个请求超时秒数，默认 180（分析接口可能较慢）
    E2E_KEEP_PDF   保存 PDF 的目录；默认保存到系统临时目录

退出码：0 = 全部校验通过；1 = 有校验失败；2 = 服务不可达/前置不满足。
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import httpx
except ImportError:  # pragma: no cover - 依赖缺失时给出明确指令
    sys.stderr.write("缺少 httpx：pip install httpx（backend/requirements.txt 已包含）\n")
    raise SystemExit(2)

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = float(os.getenv("E2E_TIMEOUT", "180"))

# 一段带 ERROR 的 syslog 样本：保证解析器能产出 error 事件，mock LLM 能给出结构化结果。
SYSLOG_TEXT = """\
Nov 12 03:12:01 D3C kernel: [ 123.456789] usb 1-1: device not responding, resetting
Nov 12 03:12:01 D3C usbhub: ERROR: port 2 over-current condition detected
Nov 12 03:12:02 D3C kernel: [ 123.457001] usb 1-1: reset SuperSpeed Gen 1 USB device number 2 using xhci_hcd
Nov 12 03:12:03 D3C usbhid: WARN: hid device probe failed, retrying with polling interval 10ms
Nov 12 03:12:05 D3C kernel: [ 123.460112] xhci_hcd 0000:00:14.0: ERROR: xHCI host controller not responding, assume dead
Nov 12 03:12:06 D3C systemd: service diagnostic-agent restarted (attempt 1/3)
Nov 12 03:12:20 D3C kernel: [ 123.475004] usb 1-1: USB disconnect, device number 2
Nov 12 03:12:21 D3C diagnostic-agent: ERROR: device heartbeat lost for 15s, usb bus unstable
"""

PDF_MAGIC = b"%PDF-"


def _force_utf8_stdout() -> None:
    """Windows 控制台默认代码页可能导致中文输出乱码，尽量切到 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover
                pass


class Checker:
    """收集并打印 PASS/FAIL 校验项。"""

    def __init__(self) -> None:
        self.checks: List[Dict[str, Any]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        ok = bool(ok)
        self.checks.append({"name": name, "ok": ok, "detail": str(detail)})
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
        return ok

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(item["ok"] for item in self.checks)


def _truncate(value: Any, limit: int = 160) -> str:
    text = str(value).replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    step: str,
    expect: int = 200,
    **kwargs: Any,
) -> httpx.Response:
    """发请求并打印基础证据；状态码不符时抛出带响应体的异常。"""
    started = time.perf_counter()
    try:
        response = client.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"{step} 请求失败（{method} {path}）：{exc}") from exc
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(
        f"  -> {method} {path} => HTTP {response.status_code} "
        f"({elapsed_ms:.0f} ms, {len(response.content)} bytes)"
    )
    if response.status_code != expect:
        raise RuntimeError(
            f"{step} 失败：期望 HTTP {expect}，实际 {response.status_code}；"
            f"响应体={_truncate(response.text, 500)!r}"
        )
    return response


def _count_pages_from_pypdf(pdf_bytes: bytes) -> Optional[int]:
    try:
        from pypdf import PdfReader  # 开发期校验用可选依赖
    except ImportError:
        return None
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return len(reader.pages)
    except Exception:  # noqa: BLE001 - 结构异常交由上层记录
        return None


def _font_evidence(pdf_bytes: bytes) -> Dict[str, Any]:
    """提取 PDF 字体资源证据：优先 pypdf，失败则退回原始字节扫描。"""
    evidence: Dict[str, Any] = {
        "pypdf_available": False,
        "font_name_found": b"STSong" in pdf_bytes,
        "base_fonts": [],
        "extracted_cjk_chars": None,
        "extracted_text_sample": "",
    }
    try:
        from pypdf import PdfReader
    except ImportError:
        return evidence

    evidence["pypdf_available"] = True
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        base_fonts: List[Tuple[str, str]] = []
        for page in reader.pages:
            resources = page.get("/Resources")
            if not resources:
                continue
            fonts = resources.get("/Font")
            if not fonts:
                continue
            for name, reference in fonts.items():
                font = reference.get_object()
                base_fonts.append((str(name), str(font.get("/BaseFont"))))
        evidence["base_fonts"] = [list(item) for item in sorted(set(base_fonts))]

        text = "".join((page.extract_text() or "") for page in reader.pages)
        evidence["extracted_cjk_chars"] = sum(
            1 for ch in text if "\u4e00" <= ch <= "\u9fff"
        )
        evidence["extracted_text_sample"] = text[:200]
    except Exception as exc:  # noqa: BLE001 - 校验工具失败不影响 HTTP 结论
        evidence["pypdf_error"] = str(exc)
    return evidence


def _count_pages_fallback(pdf_bytes: bytes) -> int:
    """无 pypdf 时用原始字节统计页面对象数量（足够用于 >=1 判定）。"""
    return len(re.findall(rb"/Type\s*/Page(?![s])", pdf_bytes))


def run(base_url: str, timeout: float) -> int:
    checker = Checker()
    started_at = datetime.now()
    started = time.perf_counter()
    evidence: Dict[str, Any] = {
        "base_url": base_url,
        "started_at": started_at.isoformat(timespec="seconds"),
        "steps": {},
        "checks": [],
    }

    print(f"== PDF 导出端到端验证 ==\n服务地址: {base_url}\n")

    client = httpx.Client(base_url=base_url, timeout=timeout)

    # ── 0. 服务可达性 + OpenAPI 路由存在性 ─────────────────────────
    print("[0/5] 服务健康检查")
    try:
        health = _request(client, "GET", "/health", step="健康检查")
    except RuntimeError as exc:
        print(f"  [FAIL] {exc}")
        print("\n结论: 服务不可达，退出码 2")
        return 2
    checker.check("GET /health 返回 200", True, _truncate(health.text))
    try:
        checker.check(
            'health.status == "ok"',
            health.json().get("status") == "ok",
            _truncate(health.text),
        )
    except ValueError:
        checker.check('health.status == "ok"', False, "响应非 JSON")

    try:
        openapi = client.get("/openapi.json")
        has_pdf_route = openapi.status_code == 200 and (
            "/api/v1/reports/{report_id}/pdf" in openapi.json().get("paths", {})
        )
    except httpx.HTTPError:
        has_pdf_route = False
    checker.check(
        "OpenAPI 中存在 /api/v1/reports/{report_id}/pdf 路由",
        has_pdf_route,
        "缺失通常说明运行的是未重建的旧镜像" if not has_pdf_route else "",
    )
    if not has_pdf_route:
        print("\n结论: 部署镜像缺少 /pdf 路由，请重建并重启 backend 后重跑。退出码 1")
        return 1

    # ── 1. 上传日志 ───────────────────────────────────────────────
    print("\n[1/5] 上传 syslog 文本")
    filename = f"pdf_e2e_{started_at.strftime('%Y%m%d_%H%M%S')}.log"
    upload = _request(
        client,
        "POST",
        "/api/v1/logs/upload",
        step="上传日志",
        files={"file": (filename, SYSLOG_TEXT.encode("utf-8"), "text/plain")},
        data={
            "device": "D3C",
            "version": "v2.3.1",
            "description": "PDF 导出端到端验证（reportlab）",
        },
    )
    log_payload = upload.json()
    log_id = int(log_payload["id"])
    evidence["steps"]["upload"] = {
        "log_id": log_id,
        "filename": log_payload.get("filename"),
        "size": log_payload.get("size"),
        "status": log_payload.get("status"),
    }
    checker.check("日志上传成功且拿到 log_id", log_id > 0, f"log_id={log_id}")

    # ── 2. 解析日志 ───────────────────────────────────────────────
    print(f"\n[2/5] 解析日志 log_id={log_id}")
    parse = _request(
        client,
        "POST",
        f"/api/v1/logs/{log_id}/parse",
        step="解析日志",
        timeout=timeout,
    )
    parse_payload = parse.json()
    parsed_events = parse_payload.get("event_count") or parse_payload.get("parsed_events")
    if parsed_events is None and isinstance(parse_payload.get("events"), list):
        parsed_events = len(parse_payload["events"])
    evidence["steps"]["parse"] = {
        "status": parse_payload.get("status"),
        "event_count": parsed_events,
    }
    checker.check(
        "解析接口返回 200 且事件数 > 0",
        parsed_events is None or int(parsed_events) > 0,
        f"event_count={parsed_events}",
    )

    # ── 3. 运行分析（mock LLM） ──────────────────────────────────
    print(f"\n[3/5] 运行分析（mock LLM）log_id={log_id}")
    analysis = _request(
        client,
        "POST",
        "/api/v1/analyses/run",
        step="运行分析",
        params={
            "log_id": log_id,
            "model": "mock",
            "user_query": "设备 USB 控制器反复复位，请分析根因并给出处理建议",
        },
        timeout=timeout,
    )
    analysis_payload = analysis.json()
    evidence["steps"]["analysis"] = {
        "analysis_id": analysis_payload.get("id"),
        "status": analysis_payload.get("status"),
        "summary": _truncate(analysis_payload.get("summary"), 200),
        "root_cause": _truncate(analysis_payload.get("root_cause"), 200),
        "model": analysis_payload.get("model"),
        "needs_clarification": analysis_payload.get("needs_clarification"),
    }
    checker.check(
        "分析状态为 completed",
        analysis_payload.get("status") == "completed",
        f"status={analysis_payload.get('status')}",
    )
    checker.check(
        "分析产出中文 summary/root_cause（中文字体路径有意义）",
        any(
            "\u4e00" <= ch <= "\u9fff"
            for ch in str(analysis_payload.get("summary") or "")
            + str(analysis_payload.get("root_cause") or "")
        ),
        _truncate(analysis_payload.get("summary"), 80),
    )

    # ── 4. 生成报告 ───────────────────────────────────────────────
    print(f"\n[4/5] 生成报告 log_id={log_id}")
    report = _request(
        client,
        "POST",
        f"/api/v1/reports/{log_id}",
        step="生成报告",
        timeout=timeout,
    )
    report_payload = report.json()
    report_id = int(report_payload["report_id"])
    evidence["steps"]["report"] = {
        "report_id": report_id,
        "title": report_payload.get("title"),
        "format": report_payload.get("format"),
        "confidence": report_payload.get("confidence"),
    }
    checker.check("报告生成成功且拿到 report_id", report_id > 0, f"report_id={report_id}")

    # ── 5. 导出 PDF ───────────────────────────────────────────────
    print(f"\n[5/5] 导出 PDF report_id={report_id}")
    pdf_response = _request(
        client,
        "GET",
        f"/api/v1/reports/{report_id}/pdf",
        step="导出 PDF",
        timeout=timeout,
    )
    content_type = pdf_response.headers.get("content-type", "")
    content_disposition = pdf_response.headers.get("content-disposition", "")
    pdf_bytes = pdf_response.content
    elapsed_ms = (time.perf_counter() - started) * 1000

    expected_disposition = f'attachment; filename="report_{report_id}.pdf"'
    pages = _count_pages_from_pypdf(pdf_bytes)
    fonts = _font_evidence(pdf_bytes)
    if pages is None:
        pages = _count_pages_fallback(pdf_bytes)
        evidence["page_count_source"] = "raw-regex-fallback"
    else:
        evidence["page_count_source"] = "pypdf"

    output_dir = Path(os.getenv("E2E_KEEP_PDF") or tempfile.mkdtemp(prefix="pdf_e2e_"))
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / f"report_{report_id}.pdf"
    pdf_path.write_bytes(pdf_bytes)

    evidence["steps"]["pdf"] = {
        "status_code": pdf_response.status_code,
        "content_type": content_type,
        "content_disposition": content_disposition,
        "size_bytes": len(pdf_bytes),
        "magic": pdf_bytes[:8].decode("latin-1", errors="replace"),
        "pages": pages,
        "font_evidence": fonts,
        "font_name_found_in_raw_bytes": fonts.get("font_name_found"),
        "duration_ms": round(elapsed_ms, 1),
        "saved_to": str(pdf_path),
    }

    checker.check("HTTP 状态 200", pdf_response.status_code == 200, str(pdf_response.status_code))
    checker.check(
        "Content-Type 为 application/pdf",
        "application/pdf" in content_type.lower(),
        content_type or "(缺失)",
    )
    checker.check("响应体以 %PDF 魔数开头", pdf_bytes.startswith(PDF_MAGIC), repr(pdf_bytes[:8]))
    checker.check("PDF 大小 > 1024 字节", len(pdf_bytes) > 1024, f"{len(pdf_bytes)} bytes")
    checker.check("PDF 可解析且页数 >= 1", isinstance(pages, int) and pages >= 1, f"pages={pages}")
    checker.check(
        "Content-Disposition 为 attachment 且文件名正确",
        content_disposition == expected_disposition,
        content_disposition or "(缺失)",
    )
    checker.check(
        "PDF 字体资源引用 STSong（中文 CID 字体生效）",
        bool(fonts.get("font_name_found")),
        str(fonts.get("base_fonts")),
    )
    if fonts.get("extracted_cjk_chars") is not None:
        checker.check(
            "pypdf 可从 PDF 提取中文字符（中文可读）",
            int(fonts["extracted_cjk_chars"]) > 0,
            f"cjk_chars={fonts['extracted_cjk_chars']}",
        )

    checker.check("PDF 已保存到磁盘供人工核对", pdf_path.is_file(), str(pdf_path))

    # ── 汇总 ─────────────────────────────────────────────────────
    evidence["checks"] = checker.checks
    evidence["passed"] = checker.passed
    evidence["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
    evidence["finished_at"] = datetime.now().isoformat(timespec="seconds")
    evidence["pdf_path"] = str(pdf_path)

    print("\n== 证据汇总 ==")
    print(f"  服务:            {base_url}")
    print(f"  日志 log_id:     {log_id}")
    print(f"  报告 report_id:  {report_id}")
    print(f"  PDF 大小:        {len(pdf_bytes)} bytes")
    print(f"  PDF 页数:        {pages}（来源: {evidence['page_count_source']}）")
    print(f"  PDF 头:          {pdf_bytes[:8]!r}")
    print(f"  Content-Type:    {content_type}")
    print(f"  Content-Disp.:   {content_disposition}")
    print(f"  STSong 证据:     {fonts.get('base_fonts') or b'STSong' in pdf_bytes}")
    print(f"  中文字符数:      {fonts.get('extracted_cjk_chars')}")
    print(f"  PDF 文件:        {pdf_path}")
    print(f"  校验通过:        {checker.passed}（{sum(1 for c in checker.checks if c['ok'])}/{len(checker.checks)}）")
    print(f"  总耗时:          {evidence['duration_ms']} ms")
    print("\nEVIDENCE_JSON: " + json.dumps(evidence, ensure_ascii=False))
    return 0 if checker.passed else 1


def main() -> int:
    _force_utf8_stdout()
    print("PDF 导出端到端验证脚本（backend/scripts/verify/pdf_export_e2e.py）")
    print(f"开始时间: {datetime.now().isoformat(timespec='seconds')}，超时: {TIMEOUT}s\n")
    try:
        return run(API_BASE_URL, TIMEOUT)
    except RuntimeError as exc:
        print(f"\n[ERROR] {exc}")
        print("\n结论: 端到端验证失败，退出码 1")
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("\n已中断")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
