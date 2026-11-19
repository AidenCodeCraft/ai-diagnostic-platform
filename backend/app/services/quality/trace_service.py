"""检索轨迹落库 — 黄金集标注与失败复盘的数据源。

原则：
  - **绝不阻断对话**：任何异常只记日志，不向上抛；
  - 用 SAVEPOINT 隔离，避免落轨迹失败把调用方的事务一起回滚；
  - 只存「当时检索到了什么」，不存用户隐私之外的原始日志内容。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import RetrievalTrace

logger = logging.getLogger(__name__)

# 与 golden sample / 回归报告绑定的流水线版本，改动检索链路时升级
# 2026-11-b：回答上下文加入「日志证据块」（P1 步骤 5），会影响命中与引用，
# 因此必须升版本，否则回归结果无法与旧轨迹归因区分。
PIPELINE_VERSION = "p1.5-quality-2026-11"

CONCLUSION_ANSWERED = "answered"
CONCLUSION_REFUSED = "refused"
CONCLUSION_ASK_SLOT = "ask_slot"
CONCLUSION_TIME_MISMATCH = "time_mismatch"
CONCLUSION_NO_KB = "no_kb_entry"


def _candidates_from_references(references: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for ref in references or []:
        try:
            candidates.append({
                "doc_id": ref.get("id") or ref.get("doc_id"),
                "title": ref.get("title"),
                "section": ref.get("section"),
                "score": ref.get("score") or ref.get("relevance_score"),
                "key": ref.get("key"),
            })
        except Exception:  # noqa: BLE001 - 单条异常不影响整体
            continue
    return candidates


def record_trace(
    db: Session,
    *,
    session_id: Optional[int],
    question: str,
    references: Optional[List[Dict[str, Any]]] = None,
    clarification: Optional[List[Dict[str, Any]]] = None,
    conclusion: str = CONCLUSION_ANSWERED,
    timings: Optional[Dict[str, Any]] = None,
    message_id: Optional[int] = None,
    log_id: Optional[int] = None,
    kb_candidates: Optional[List[Dict[str, Any]]] = None,
    log_patterns: Optional[Dict[str, Any]] = None,
    log_blocks: Optional[Dict[str, Any]] = None,
) -> Optional[RetrievalTrace]:
    """记录一次检索轨迹；失败返回 None，绝不抛异常。"""
    try:
        trace = RetrievalTrace(
            session_id=session_id,
            message_id=message_id,
            log_id=log_id,
            question=question or "",
            kb_candidates={
                "candidates": kb_candidates if kb_candidates is not None
                else _candidates_from_references(references),
                "clarification": clarification or [],
            },
            log_patterns=log_patterns,
            log_blocks=log_blocks,
            timings=timings or {},
            conclusion=conclusion,
            pipeline_version=PIPELINE_VERSION,
        )
        with db.begin_nested():
            db.add(trace)
        db.commit()
        return trace
    except Exception:  # noqa: BLE001 - 轨迹是可观测性附产物，不允许影响主流程
        logger.warning("[RetrievalTrace] record failed", exc_info=True)
        return None


def resolve_conclusion(
    direct_reply: Optional[str], clarification: Optional[List[Dict[str, Any]]],
) -> str:
    """由「是否直接回复」和「是否有追问」推出结论分支。

    用于把一次对话归类到 answered / ask_slot / refused，
    回归集据此对比 expected_conclusion。
    """
    if direct_reply is None:
        return CONCLUSION_ANSWERED
    return CONCLUSION_ASK_SLOT if clarification else CONCLUSION_REFUSED
