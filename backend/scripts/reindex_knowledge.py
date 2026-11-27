"""知识库向量回填 CLI。

用法（在 backend/ 目录、ML 镜像或已装 sentence-transformers 的环境内执行）：

    # 1) 自检：确认是语义 embedding + 集合就绪（不写入）
    python -m scripts.reindex_knowledge --check

    # 2) 先空跑统计（不写入）
    python -m scripts.reindex_knowledge --dry-run

    # 3) 正式回填（可断点续跑：--start-id）
    python -m scripts.reindex_knowledge --batch-log 50

    # 4) 回填后校验
    python -m scripts.reindex_knowledge --verify

回填期间建议保持知识库只读（管理端暂停编辑），避免「回填到一半文档被改」。
"""

from __future__ import annotations

import argparse
import sys

from app.core.logging_config import get_logger
from app.database import session as session_module
from app.services.knowledge.reindex_service import (
    ReindexError,
    ReindexStats,
    check_environment,
    run_reindex,
)

logger = get_logger(__name__)


def _print_progress(stats: ReindexStats, every: int) -> None:
    if stats.indexed_docs and stats.indexed_docs % every == 0:
        print(f"  已处理 {stats.indexed_docs}/{stats.total_docs} 篇，章节 {stats.total_chunks} 个")


def _verify(vector_service) -> int:
    """回填后校验：集合实体数 + 抽样检索是否返回章节级结果。"""
    info = getattr(vector_service, "collection_info", None) or {}
    num_entities = info.get("num_entities")
    print(f"[verify] collection={getattr(vector_service, 'collection_name', '')} entities={num_entities}")
    if not num_entities:
        print("[verify] ✗ 集合为空：回填未生效")
        return 1

    hits = vector_service.search("设备版本号如何查询", top_k=3)
    if not hits:
        print("[verify] ✗ 抽样检索无结果：检查 embedding 与索引")
        return 1
    print("[verify] 抽样检索命中：")
    for hit in hits:
        print(
            f"   - doc {hit.get('id')} / {hit.get('section') or '—'} "
            f"/ score={hit.get('score'):.3f} / {str(hit.get('content'))[:40]}"
        )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="按章节级 schema 回填知识库向量")
    parser.add_argument("--check", action="store_true", help="只做环境自检")
    parser.add_argument("--dry-run", action="store_true", help="只统计文档，不写入向量")
    parser.add_argument("--verify", action="store_true", help="只做回填后校验")
    parser.add_argument("--start-id", type=int, default=0, help="从该文档 ID 之后开始（断点续跑）")
    parser.add_argument("--limit", type=int, default=None, help="最多处理文档数")
    parser.add_argument("--batch-log", type=int, default=50, help="每处理 N 篇打印一次进度")
    args = parser.parse_args(argv)

    db = session_module.create_session()
    try:
        if args.verify:
            from app.services.knowledge.vector_service import get_vector_service

            return _verify(get_vector_service())

        try:
            env = check_environment()
        except ReindexError as exc:
            print(f"[check] ✗ {exc}")
            return 2

        print(
            f"[check] ✓ provider={env['provider']} dim={env['dimension']} "
            f"collection={env['collection']}"
        )
        if args.check:
            return 0

        print(f"[reindex] dry_run={args.dry_run} start_id={args.start_id} limit={args.limit}")
        stats = run_reindex(
            db,
            start_id=args.start_id,
            limit=args.limit,
            dry_run=args.dry_run,
            progress=lambda s: _print_progress(s, args.batch_log),
        )
        summary = stats.summary()
        print("[reindex] 完成：" + ", ".join(f"{k}={v}" for k, v in summary.items()))
        if stats.failed:
            for row in stats.failed[:10]:
                print(f"   ✗ doc {row['doc_id']}: {row['error']}")
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
