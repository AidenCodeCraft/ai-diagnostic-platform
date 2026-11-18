"""黄金集检索回归的共享夹具。

数据来源（按优先级）：
  1. 环境变量 GOLDEN_SAMPLES_FILE 指向的 JSON（由 GET /api/v1/quality/golden-samples/export 导出）；
  2. 数据库里 status=approved 的样本（本地/预发环境）；
  3. 都没有 → 整个目录 skip，CI 不会因为「还没标样本」而变红。

设计约束：
  - 只调用检索层，不调用 LLM —— 快检零成本、结果确定；
  - 阈值可被环境变量覆盖（REGRESSION_RECALL_AT_5 等），但**下调阈值必须单独提交**。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import pytest


def _load_from_file() -> List[Dict[str, Any]]:
    path = os.getenv("GOLDEN_SAMPLES_FILE")
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload.get("items", payload if isinstance(payload, list) else [])


def _load_from_db() -> List[Dict[str, Any]]:
    try:
        from app.database import session as session_module
        from app.services.quality import GoldenSampleService

        db = session_module.create_session()
        try:
            return GoldenSampleService(db).export_approved()
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - 库不可用视作没有样本
        return []


@pytest.fixture(scope="session")
def golden_samples() -> List[Dict[str, Any]]:
    samples = _load_from_file() or _load_from_db()
    if not samples:
        pytest.skip(
            "暂无 approved 黄金样本（GOLDEN_SAMPLES_FILE 未设置且库中为空）；"
            "请先在对话界面标注并通过审核"
        )
    return samples


@pytest.fixture(scope="session")
def thresholds() -> Dict[str, float]:
    return {
        "recall_at_5": float(os.getenv("REGRESSION_RECALL_AT_5", "0.85")),
        "mrr": float(os.getenv("REGRESSION_MRR", "0.70")),
    }
