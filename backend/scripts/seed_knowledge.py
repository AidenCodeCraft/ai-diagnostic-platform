"""知识库种子数据脚本（逻辑位于 app.services.knowledge.seed_service）。

用法（在 backend/ 目录下）:
    python -m scripts.seed_knowledge          # 创建缺失的示例知识
    python -m scripts.seed_knowledge --reset  # 先删除同名示例再重建
"""

from __future__ import annotations

import argparse
from typing import Tuple

from app.services.knowledge.seed_service import SAMPLE_DOCS, seed  # noqa: F401 - re-export


def main() -> Tuple[int, int, int]:
    parser = argparse.ArgumentParser(description="创建知识库示例数据")
    parser.add_argument("--reset", action="store_true", help="先删除同名示例再重建")
    args = parser.parse_args()

    from app.database import session as session_module

    db = session_module.create_session()
    try:
        stats = seed(db, reset=args.reset)
    finally:
        db.close()
    print(
        f"created={stats['created']} skipped={stats['skipped']} deleted={stats['deleted']}"
    )
    return stats["created"], stats["skipped"], stats["deleted"]


if __name__ == "__main__":
    main()
