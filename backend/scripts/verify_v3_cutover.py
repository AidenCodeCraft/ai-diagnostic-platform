"""v3 集合切流验证（V1 + V2）一条命令跑完。

步骤：预检 → 重建/回填 → 抽样检索校验 → 输出报告与结论。

用法::

    # 只看环境和规模，不写入
    python -m scripts.verify_v3_cutover --dry-run

    # 全流程（会重建集合与回填）
    python -m scripts.verify_v3_cutover \
        --question "进出站日志中搜索什么" \
        --expect-doc FAQ --expect-section "第 5 节"

    # 只做检索校验（回填已完成）
    python -m scripts.verify_v3_cutover --verify-only --question "..."
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_REPORT = "reports/v3_cutover.json"


def _server_version() -> str:
    """读取服务端版本（get_server_version 需要已建立的连接）。"""
    try:
        from pymilvus import connections, utility

        from app.core.config import settings

        try:
            connections.connect(
                host=str(getattr(settings, "MILVUS_HOST", "localhost")),
                port=str(getattr(settings, "MILVUS_PORT", 19530)),
            )
        except Exception:  # noqa: BLE001 - 已连接时重复 connect 也会抛，忽略
            pass
        return str(utility.get_server_version())
    except Exception as exc:  # noqa: BLE001
        return f"unknown ({exc})"


def _sample_queries(limit: int = 3) -> List[str]:
    """没有指定问题时，用几条通用问句证明检索链路通。"""
    return ["设备无法联网", "4G 注册失败", "日志中有哪些错误"][:limit]


def _check_hits(hits: List[Dict[str, Any]]) -> Dict[str, Any]:
    """V2：所有命中必须是知识章节，不能混入日志证据块。"""
    types = {str(hit.get("chunk_type") or "") for hit in hits}
    sources = {str(hit.get("source") or "") for hit in hits}
    return {
        "ok": bool(hits) and types <= {"section"} and sources <= {"knowledge"},
        "chunk_types": sorted(types),
        "sources": sorted(sources),
        "hits": len(hits),
    }


def _acceptance_hit(
    hits: List[Dict[str, Any]], expect_doc: Optional[str], expect_section: Optional[str],
) -> Dict[str, Any]:
    """验收用例：《FAQ》第 5 节应被召回（旧实现只召回《线路》第 1 节）。"""
    if not (expect_doc or expect_section):
        return {"ok": None, "detail": "未指定 --expect-doc/--expect-section，跳过"}

    for rank, hit in enumerate(hits, start=1):
        title = str(hit.get("title") or "")
        section = str(hit.get("section") or "")
        doc_ok = expect_doc.lower() in title.lower() if expect_doc else True
        section_ok = expect_section in section if expect_section else True
        if doc_ok and section_ok:
            return {"ok": True, "rank": rank, "title": title, "section": section}

    top = [
        {"rank": i, "title": h.get("title"), "section": h.get("section")}
        for i, h in enumerate(hits[:5], start=1)
    ]
    return {"ok": False, "expected": {"doc": expect_doc, "section": expect_section}, "top5": top}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="v3 集合切流验证（重建 + 回填 + 检索校验）")
    parser.add_argument("--dry-run", action="store_true", help="只预检与统计，不写向量")
    parser.add_argument("--verify-only", action="store_true", help="跳过回填，只做检索校验")
    parser.add_argument("--limit", type=int, default=None, help="最多回填多少篇文档")
    parser.add_argument("--question", default="", help="验收提问（真实失败样本）")
    parser.add_argument("--expect-doc", default="", help="期望命中的文档标题关键字，如 FAQ")
    parser.add_argument("--expect-section", default="", help="期望命中的章节关键字，如 第 5 节")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    args = parser.parse_args(argv)

    from app.database.session import create_session
    from app.services.knowledge.embedding import get_embedder
    from app.services.knowledge.reindex_service import (
        ReindexError,
        check_environment,
        run_reindex,
    )
    from app.services.knowledge.vector_service import (
        COLLECTION_SCHEMA_VERSION,
        KNOWLEDGE_CHUNK_TYPES,
        get_vector_service,
    )

    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": COLLECTION_SCHEMA_VERSION,
        "milvus_server_version": _server_version(),
        "checks": [],
        "verdict": "unknown",
    }

    vector_service = get_vector_service()
    embedder = get_embedder()
    report["collection"] = getattr(vector_service, "collection_name", "")
    report["embedding"] = {
        "provider": getattr(embedder, "provider_name", type(embedder).__name__),
        "dimension": getattr(embedder, "dimension", None),
    }

    # ── 1. 预检 ────────────────────────────────────────────────
    try:
        env = check_environment(vector_service=vector_service, embedder=embedder)
        report["checks"].append({"name": "preflight", "ok": True, "detail": env})
    except ReindexError as exc:
        report["checks"].append({"name": "preflight", "ok": False, "detail": str(exc)})
        report["verdict"] = "blocked"
        _write_report(report, args.report)
        print(f"[FAIL] 预检未通过：{exc}")
        return 2

    # ── 2. 回填 ────────────────────────────────────────────────
    db = create_session()
    try:
        if args.verify_only:
            report["checks"].append(
                {"name": "reindex", "ok": True, "detail": "skipped (--verify-only)"},
            )
        else:
            stats = run_reindex(
                db,
                limit=args.limit,
                dry_run=args.dry_run,
                progress=lambda s: print(
                    f"  回填进度 {s.indexed_docs}/{s.total_docs} 文档，"
                    f"{s.total_chunks} 章节，失败 {len(s.failed)}"
                ),
            )
            summary = stats.summary()
            report["reindex"] = summary
            ok = summary.get("failed_docs", 0) == 0 and summary.get("total_chunks", 0) > 0
            report["checks"].append({"name": "reindex", "ok": ok, "detail": summary})
            if args.dry_run:
                report["verdict"] = "dry-run"
                _write_report(report, args.report)
                print("[OK] 预检通过（dry-run，未写入向量）")
                return 0

        # ── 3. 检索校验（V2）──────────────────────────────────
        questions = [args.question] if args.question else _sample_queries()
        retrieval_ok = True
        acceptance_ok: Optional[bool] = None
        details: List[Dict[str, Any]] = []

        for question in questions:
            hits = vector_service.search(
                question, top_k=args.top_k, chunk_types=list(KNOWLEDGE_CHUNK_TYPES),
            )
            check = _check_hits(hits)
            retrieval_ok = retrieval_ok and check["ok"]
            entry = {"question": question, **check}
            if question == args.question and args.question:
                acceptance = _acceptance_hit(hits, args.expect_doc, args.expect_section)
                entry["acceptance"] = acceptance
                if acceptance.get("ok") is not None:
                    acceptance_ok = bool(acceptance["ok"])
            details.append(entry)

        report["checks"].append(
            {"name": "chunk_type_filter", "ok": retrieval_ok, "detail": details},
        )
        if acceptance_ok is not None:
            report["checks"].append(
                {"name": "acceptance_case", "ok": acceptance_ok,
                 "detail": "《FAQ》第 5 节应被召回"},
            )

        all_ok = all(c["ok"] for c in report["checks"] if c.get("ok") is not None)
        report["verdict"] = "ready" if all_ok else "not-ready"
        _write_report(report, args.report)

        print()
        for check in report["checks"]:
            print(f"  {'✓' if check['ok'] else '✗'} {check['name']}")
        print(f"\n结论：{report['verdict']}（报告：{args.report}）")
        return 0 if all_ok else 1
    finally:
        db.close()


def _write_report(report: Dict[str, Any], path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
