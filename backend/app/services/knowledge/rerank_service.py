"""检索后精排 — Cross-Encoder（BGE-Reranker）接在召回之后、拼上下文之前。

为什么必须在前端链路里做：
    向量 + BM25 的融合分只反映「词面/语义接近」，不判断「这段文字是否真的回答了
    这个问题」。Cross-Encoder 把 (问题, 章节) 成对送进模型打分，是召回之后唯一能
    显著提升 top-k 准确度的环节。此前它只挂在未被调用的 RAGService 上，等于没生效。

设计约束：
  - 缺 sentence-transformers / 模型加载失败 / 推理异常 → 一律跳过，返回原顺序，
    绝不阻断回答（精排是增强项，不是依赖项）；
  - 只对前 RERANKER_TOP_N 条候选做精排（CPU 上是线性成本），其余直接丢弃；
  - 展示分按本次最高分归一化，仅在同一回答内可比。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# 单条候选送入精排的最大字符数（BGE-Reranker 输入上限 512 token，中文约 500 字）
MAX_DOC_CHARS = 1000

_reranker: Any = None
_reranker_failed = False


def get_reranker() -> Optional[Any]:
    """惰性加载精排模型；失败只记一次日志，后续调用直接返回 None。"""
    global _reranker, _reranker_failed
    if _reranker is not None:
        return _reranker
    if _reranker_failed:
        return None
    if not bool(getattr(settings, "RERANKER_ENABLED", True)):
        _reranker_failed = True
        logger.info("[Rerank] disabled by config")
        return None

    try:
        from app.services.core.config import RerankerConfig
        from app.services.knowledge.rerankers import CrossEncoderReranker

        config = RerankerConfig(
            model_name=str(getattr(settings, "RERANKER_MODEL", "BAAI/bge-reranker-base")),
            top_k=int(getattr(settings, "RERANKER_TOP_N", 30) or 30),
        )
        _reranker = CrossEncoderReranker(config)
        logger.info("[Rerank] model loaded: %s", config.model_name)
        return _reranker
    except Exception as exc:  # noqa: BLE001 - 缺依赖/无模型/显存不足都走这里
        _reranker_failed = True
        logger.warning("[Rerank] unavailable, falling back to retrieval order: %s", exc)
        return None


def reset_reranker() -> None:
    """测试用：清空单例状态。"""
    global _reranker, _reranker_failed
    _reranker = None
    _reranker_failed = False


def _doc_text(item: Dict[str, Any], text_key: str) -> str:
    text = item.get(text_key) or item.get("snippet") or item.get("_full_content") or ""
    return str(text)[:MAX_DOC_CHARS]


def rerank_items(
    query: str,
    items: List[Dict[str, Any]],
    *,
    text_key: str = "snippet",
    top_n: Optional[int] = None,
    keep: Optional[int] = None,
    reranker: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """对召回结果精排。

    Args:
        query: 用户问题（单个检索单元）
        items: 召回结果（按融合分排序）
        text_key: 用于精排的文本字段
        top_n: 参与精排的候选数，默认取配置
        keep: 精排后保留条数，默认等于 top_n
        reranker: 显式传入的精排器（测试用）；None 时惰性加载

    Returns:
        重排后的列表（含 `_rerank_score`，`relevance_score` 被归一化覆盖）；
        无精排器或推理失败时返回原列表。
    """
    if not items or not (query or "").strip():
        return items

    engine = reranker if reranker is not None else get_reranker()
    if engine is None:
        return items

    top_n = int(top_n or getattr(settings, "RERANKER_TOP_N", 30) or 30)
    keep = int(keep or top_n)
    head = list(items[:top_n])
    if not head:
        return items

    docs = [_doc_text(item, text_key) for item in head]
    if not any(docs):
        return items

    try:
        ranked = engine.rerank(query, docs, top_k=min(keep, len(docs)))
    except Exception as exc:  # noqa: BLE001 - 精排失败按原顺序返回
        logger.warning("[Rerank] inference failed, keeping retrieval order: %s", exc)
        return items

    if not ranked:
        return items

    ordered: List[Dict[str, Any]] = []
    for idx, score in ranked:
        if idx < 0 or idx >= len(head):
            continue
        enriched = dict(head[idx])
        enriched["_retrieval_score"] = enriched.get("relevance_score")
        enriched["_rerank_score"] = float(score)
        ordered.append(enriched)

    if not ordered:
        return items

    top_score = max((item["_rerank_score"] for item in ordered), default=0.0)
    threshold = float(getattr(settings, "RERANKER_SCORE_THRESHOLD", 0.0) or 0.0)
    for item in ordered:
        raw = item["_rerank_score"]
        item["relevance_score"] = round(raw / top_score, 4) if top_score > 0 else 0.0

    filtered = [item for item in ordered if item["relevance_score"] >= threshold]
    result = filtered or ordered
    logger.info(
        "[Rerank] query=%.30s candidates=%d kept=%d top=%.3f",
        query, len(head), len(result), top_score,
    )
    return result
