"""知识库索引漂移检查 —— 内容改了但没回填时立刻报警。

为什么需要这个脚本：
    检索只在「向量块能按 content_hash 映射回当前章节」时才生效。
    内容改过而索引没重建时，dense 检索会把 top-k 名额全花在**已经不存在**的
    旧块上，映射失败后整段候选被丢弃 —— 表现是「某篇大文档霸榜、正确答案不出现」，
    而日志里没有任何报错。这次事故就是这么发生的：集合 1192 条实体，
    当前内容只需 174 条。

判据（任一不满足即视为漂移）：
    1. 每篇 active 非目录文档：当前应产生的 content_hash 集合 == 集合里的 hash 集合；
    2. 集合里不存在 doc_id 不在库内的孤儿块；
    3. 实体总数 == 应产生块数。

用法（backend/ 目录下，需 Milvus 可连通）：

    python -m scripts.check_knowledge_index            # 只检查，漂移时退出码 1
    python -m scripts.check_knowledge_index --json     # 机器可读
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from typing import Dict, List, Set

from app.core.logging_config import get_logger
from app.database import session as session_module
from app.models import KnowledgeDocument
from app.services.knowledge.section_search import build_section_chunks

logger = get_logger(__name__)


def _expected_hashes(db) -> Dict[int, Set[str]]:
    """按检索粒度（章节级）算出每篇文档当前应有的块 hash。"""
    docs = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.status == "active")
        .filter(KnowledgeDocument.doc_type != "folder")
        .all()
    )
    expected: Dict[int, Set[str]] = defaultdict(set)
    for doc in docs:
        chunks = build_section_chunks([doc])
        expected[doc.id] = {c.content_hash for c in chunks if c.content_hash}
    return expected


def _indexed_hashes(settings) -> Dict[int, Set[str]]:
    """读出集合里实际存在的 (doc_id -> hash 集合)。"""
    from pymilvus import Collection, connections

    connections.connect(alias="default", host=settings.MILVUS_HOST, port=str(settings.MILVUS_PORT))
    col = Collection(settings.MILVUS_COLLECTION)
    col.load()
    rows = col.query(
        expr="chunk_type == 'section'",
        output_fields=["doc_id", "content_hash"],
        limit=16384,
    )
    indexed: Dict[int, Set[str]] = defaultdict(set)
    for row in rows:
        indexed[int(row["doc_id"])].add(str(row.get("content_hash") or ""))
    return indexed


def check(db=None) -> dict:
    """返回漂移报告；drift=True 表示索引与内容不一致。"""
    from app.core.config import settings

    own_session = db is None
    db = db or session_module.create_session()
    try:
        expected = _expected_hashes(db)
        indexed = _indexed_hashes(settings)
    finally:
        if own_session:
            db.close()

    rows: List[dict] = []
    drifted = False
    for doc_id in sorted(set(expected) | set(indexed)):
        exp = {h for h in expected.get(doc_id, set()) if h}
        got = {h for h in indexed.get(doc_id, set()) if h}
        missing, stale = exp - got, got - exp
        if not (missing or stale):
            continue
        drifted = True
        rows.append(
            {
                "doc_id": doc_id,
                "missing": len(missing),
                "stale": len(stale),
                "expected": len(exp),
                "indexed": len(got),
            }
        )

    exp_total = sum(len(v) for v in expected.values())
    got_total = sum(len(v) for v in indexed.values())
    return {
        "drift": drifted or exp_total != got_total,
        "collection": settings.MILVUS_COLLECTION,
        "expected_total": exp_total,
        "indexed_total": got_total,
        "docs": rows,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="检查知识库索引是否与文档内容一致")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    report = check()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"[index] collection={report['collection']} "
            f"expected={report['expected_total']} indexed={report['indexed_total']}"
        )
        for row in report["docs"][:20]:
            print(
                f"   ✗ doc {row['doc_id']}: 期望 {row['expected']} 块 / 集合 {row['indexed']} 块 "
                f"（缺 {row['missing']}、过期 {row['stale']}）"
            )
        if report["drift"]:
            print("[index] ✗ 索引漂移：运行 python -m scripts.reindex_knowledge 回填")
        else:
            print("[index] ✓ 索引与内容一致")
    return 1 if report["drift"] else 0


if __name__ == "__main__":
    sys.exit(main())
