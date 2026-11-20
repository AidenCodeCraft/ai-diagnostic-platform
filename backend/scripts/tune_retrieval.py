"""检索参数调优（RRF k / 两路权重）——用黄金集当标尺。

用法::

    python -m scripts.tune_retrieval --dry-run    # 打印网格，不跑检索
    python -m scripts.tune_retrieval              # 跑网格并打印排行

口径与回归 harness 一致：章节主题命中算 recall@5，名次倒数算 MRR。
调参后必须跑一次 pytest tests/regression -m golden，确认不是只在网格内好看。
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# k 越小越看重头部名次；权重用于表达「更信任哪一路」
K_GRID = (20, 40, 60, 80)
WEIGHT_GRID = ((1.0, 1.0), (1.5, 1.0), (1.0, 1.5), (2.0, 1.0))


def _section_hit(item: Dict[str, Any], sample: Dict[str, Any]) -> bool:
    for entry in sample.get("kb_expected") or []:
        if not isinstance(entry, dict) or entry.get("doc_id") is None:
            continue
        if int(item.get("id") or 0) != int(entry["doc_id"]):
            continue
        section = str(entry.get("section") or "").strip()
        if not section:
            return True
        haystack = f"{item.get('section') or ''} {item.get('title') or ''}"
        if section in haystack:
            return True
    return False


def evaluate(db, samples: List[Dict[str, Any]], page_size: int = 5) -> Tuple[float, float]:
    from app.services.knowledge.knowledge_service import KnowledgeService

    service = KnowledgeService(db)
    recalls = 0
    rr_sum = 0.0
    total = 0
    for sample in samples:
        if not (sample.get("kb_expected") or []):
            continue
        total += 1
        result = service.search(sample["question"], page=1, page_size=page_size, sections=True)
        items = result.get("items") or []
        rank = next(
            (i + 1 for i, item in enumerate(items) if _section_hit(item, sample)),
            0,
        )
        if 0 < rank <= page_size:
            recalls += 1
        if rank:
            rr_sum += 1.0 / rank
    if not total:
        return 0.0, 0.0
    return recalls / total, rr_sum / total


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="用黄金集调优 RRF 参数")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args(argv)

    combos = list(itertools.product(K_GRID, WEIGHT_GRID))

    if args.dry_run:
        for k, (sparse, dense) in combos:
            print(f"k={k:>3} sparse={sparse} dense={dense}")
        print(f"\n共 {len(combos)} 组")
        return 0

    from app.core.config import settings
    from app.database.session import create_session
    from app.services.quality import GoldenSampleService

    db = create_session()
    try:
        samples = GoldenSampleService(db).export_approved()
        if not samples:
            print("[FAIL] 库里没有 approved 样本")
            return 2
        print(f"样本 {len(samples)} 条，开始扫描 {len(combos)} 组参数…\n")

        rows: List[Dict[str, Any]] = []
        for k, (sparse, dense) in combos:
            settings.RRF_K = k
            settings.RRF_WEIGHT_SPARSE = sparse
            settings.RRF_WEIGHT_DENSE = dense
            recall, mrr = evaluate(db, samples)
            rows.append({"k": k, "sparse": sparse, "dense": dense,
                         "recall_at_5": round(recall, 4), "mrr": round(mrr, 4)})
            print(f"  k={k:>3} sparse={sparse} dense={dense} → "
                  f"recall@5={recall:.4f} mrr={mrr:.4f}")

        rows.sort(key=lambda r: (r["recall_at_5"], r["mrr"]), reverse=True)
        print(f"\nTop {args.top}:")
        for row in rows[: args.top]:
            print(f"  k={row['k']:>3} sparse={row['sparse']} dense={row['dense']} "
                  f"recall@5={row['recall_at_5']} mrr={row['mrr']}")
        best = rows[0]
        print(f"\n建议：RRF_K={best['k']} RRF_WEIGHT_SPARSE={best['sparse']} "
              f"RRF_WEIGHT_DENSE={best['dense']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
