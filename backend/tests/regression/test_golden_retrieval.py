"""黄金集检索回归（fast 套件：只调检索层，不调 LLM）。

指标口径：
  - recall@5：期望命中的文档出现在前 5 条的比例；
  - MRR：期望文档首次出现名次的倒数均值。

为什么只测检索不测生成：生成侧的人为判分成本高、波动大；检索是生成的上限，
召回不达标时生成再好也是无源之水。语义正确性判分放在夜间 full 套件。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

pytestmark = pytest.mark.golden

REPORT_DIR = Path(__file__).resolve().parents[2] / "reports"


def _retrieve(db, question: str, page_size: int = 5) -> List[Dict[str, Any]]:
    from app.services.knowledge.knowledge_service import KnowledgeService

    result = KnowledgeService(db).search(question, page=1, page_size=page_size)
    return result.get("items", [])


def _expected_doc_ids(sample: Dict[str, Any]) -> set:
    return {
        int(entry["doc_id"])
        for entry in (sample.get("kb_expected") or [])
        if isinstance(entry, dict) and entry.get("doc_id") is not None
    }


@pytest.fixture(scope="module")
def db():
    from app.database import session as session_module

    session = session_module.create_session()
    try:
        yield session
    finally:
        session.close()


def test_golden_retrieval_quality(db, golden_samples, thresholds):
    from app.core.config import settings

    if not getattr(settings, "MILVUS_ENABLED", False):
        pytest.skip("MILVUS_ENABLED=false：语义检索回归需要真实向量库")

    scored: List[Dict[str, Any]] = []
    ranks: List[int] = []
    for sample in golden_samples:
        expected = _expected_doc_ids(sample)
        if not expected:
            continue
        items = _retrieve(db, sample["question"])
        got = [int(item["id"]) for item in items]
        rank = next((i + 1 for i, doc_id in enumerate(got) if doc_id in expected), 0)
        ranks.append(rank)
        scored.append({
            "sample_id": sample.get("id"),
            "question": sample["question"],
            "expected": sorted(expected),
            "retrieved": got,
            "rank": rank,
        })

    if not scored:
        pytest.skip("approved 样本里没有被 retrival 检索引用的期望章节（kb_expected 为空）")

    recall_at_5 = sum(1 for r in ranks if 0 < r <= 5) / len(ranks)
    mrr = sum((1.0 / r) for r in ranks if r > 0) / len(ranks)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "total": len(scored),
        "recall_at_5": round(recall_at_5, 4),
        "mrr": round(mrr, 4),
        "thresholds": thresholds,
        "pipeline_version": os.getenv("REGRESSION_PIPELINE_VERSION", ""),
        "failures": [row for row in scored if row["rank"] == 0 or row["rank"] > 5],
        "details": scored,
    }
    (REPORT_DIR / "golden_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    assert recall_at_5 >= thresholds["recall_at_5"], (
        f"recall@5={recall_at_5:.3f} 低于门槛 {thresholds['recall_at_5']:.3f}；"
        f"失败样本见 {REPORT_DIR / 'golden_report.json'}"
    )
    assert mrr >= thresholds["mrr"], (
        f"MRR={mrr:.3f} 低于门槛 {thresholds['mrr']:.3f}"
    )
