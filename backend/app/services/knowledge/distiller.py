"""自进化蒸馏器 — 把一次「已解决」的问答蒸馏为知识库候选（draft）。

流程：
  1. 定位目标 assistant 消息及其前置 user 问题
  2. LLM 蒸馏为结构化诊断剧本；失败时启发式兜底
  3. 去重（与现有 draft/active profile 比对）
  4. 创建 draft 知识条目 + draft 诊断剧本（source=ai_candidate），等待人工审核
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models import ChatMessage, KnowledgeDiagnosisProfile
from app.services.knowledge.knowledge_service import KnowledgeService
from app.services.knowledge.profile_service import KnowledgeProfileService
from app.services.knowledge.provider_registry import ProviderRegistry
from app.services.prompts.knowledge_distill_prompt import KnowledgeDistillPrompt

logger = get_logger(__name__)

MAX_ANSWER_CHARS = 4000
INITIAL_CONFIDENCE = 0.3


class KnowledgeDistiller:
    """把「已解决」问答蒸馏为知识库候选。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.knowledge = KnowledgeService(db)
        self.profiles = KnowledgeProfileService(db)

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------

    def distill_for_message(
        self, session_id: int, message_id: int, model: Optional[str] = None,
    ) -> Optional[KnowledgeDiagnosisProfile]:
        """蒸馏单条 assistant 消息。返回候选 profile；跳过/失败返回 None。"""
        target = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.id == message_id, ChatMessage.session_id == session_id)
            .first()
        )
        if target is None or target.role != "assistant":
            return None

        question = self._find_question(session_id, target)
        if not question:
            return None

        answer = str(target.content or "")
        candidate = self._build_candidate(question, answer, model)
        if candidate is None:
            return None
        if self._similar_exists(candidate):
            logger.info("[Distiller] similar draft/active profile exists, skip")
            return None
        return self._create_draft(question, answer, candidate)

    # ------------------------------------------------------------------
    # 问题定位
    # ------------------------------------------------------------------

    def _find_question(self, session_id: int, target: ChatMessage) -> str:
        messages = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .all()
        )
        target_id = target.id
        for msg in reversed(messages):
            if msg.id == target_id:
                continue
            if msg.role == "user":
                # 只要目标消息之前的最后一条 user 消息
                if msg.created_at and target.created_at and msg.created_at <= target.created_at:
                    return str(msg.content or "").strip()
                if not msg.created_at or not target.created_at:
                    return str(msg.content or "").strip()
        return ""

    # ------------------------------------------------------------------
    # 蒸馏
    # ------------------------------------------------------------------

    def _build_candidate(
        self, question: str, answer: str, model: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        payload = self._llm_extract(question, answer, model)
        if payload is None:
            payload = self._heuristic_extract(question)
        if not payload:
            return None
        return self._normalize(payload)

    def _llm_extract(
        self, question: str, answer: str, model: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        try:
            provider = ProviderRegistry().get_provider(model or "mock")
            raw = provider.chat(KnowledgeDistillPrompt.build_messages(question, answer))
            parsed = self._parse_json(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception as exc:
            logger.warning("[Distiller] LLM distill failed, fallback to heuristic: %s", exc)
        return None

    @staticmethod
    def _parse_json(raw: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, str) or not raw.strip():
            return None
        text = raw.strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                pass
        return None

    @staticmethod
    def _heuristic_extract(question: str) -> Dict[str, Any]:
        cn = re.findall(r"[\u4e00-\u9fff]{2,6}", question)
        en = re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", question)
        keywords = list(dict.fromkeys(cn + en))[:8]
        return {
            "symptom": question[:200],
            "environment": "",
            "log_keywords": keywords,
            "log_patterns": [],
            "negative_patterns": [],
            "expected": "",
            "root_cause": "",
            "solution": "",
        }

    @staticmethod
    def _normalize(payload: Dict[str, Any]) -> Dict[str, Any]:
        def _str(key: str) -> str:
            value = payload.get(key)
            return str(value).strip() if value is not None else ""

        def _list(key: str) -> List[str]:
            value = payload.get(key)
            if isinstance(value, str):
                return [v.strip() for v in re.split(r"[\n,]，", value) if v.strip()]
            if isinstance(value, (list, tuple)):
                return [str(v).strip() for v in value if str(v).strip()]
            return []

        return {
            "symptom": _str("symptom"),
            "environment": _str("environment"),
            "log_keywords": _list("log_keywords"),
            "log_patterns": _list("log_patterns"),
            "negative_patterns": _list("negative_patterns"),
            "expected": _str("expected"),
            "root_cause": _str("root_cause"),
            "solution": _str("solution"),
        }

    # ------------------------------------------------------------------
    # 去重与落库
    # ------------------------------------------------------------------

    def _similar_exists(self, candidate: Dict[str, Any]) -> bool:
        symptom = (candidate.get("symptom") or "").strip()
        keywords = {k.lower() for k in (candidate.get("log_keywords") or [])}
        existing = (
            self.db.query(KnowledgeDiagnosisProfile)
            .filter(KnowledgeDiagnosisProfile.status.in_(["draft", "active"]))
            .all()
        )
        for profile in existing:
            ps = (profile.symptom or "").strip()
            if symptom and ps and (symptom in ps or ps in symptom):
                return True
            pks = {k.lower() for k in (profile.log_keywords or [])}
            if keywords and pks and len(keywords & pks) >= 2:
                return True
        return False

    def _create_draft(
        self, question: str, answer: str, candidate: Dict[str, Any],
    ) -> Optional[KnowledgeDiagnosisProfile]:
        symptom = (candidate.get("symptom") or "").strip() or question[:60]
        title = f"[自进化候选] {symptom[:30]}"
        content = (
            f"## 问题\n\n{question}\n\n"
            f"## 处理结果\n\n{answer[:MAX_ANSWER_CHARS]}"
        )
        try:
            doc = self.knowledge.create({
                "title": title,
                "content": content,
                "doc_type": "case",
                "category": "self-evolution",
                "status": "draft",
            })
            profile = self.profiles.upsert(doc.id, {
                **candidate,
                "confidence": INITIAL_CONFIDENCE,
                "status": "draft",
                "source": "ai_candidate",
            })
            logger.info(
                "[Distiller] created draft candidate profile=%s doc=%s", profile.id, doc.id,
            )
            return profile
        except Exception as exc:
            logger.error("[Distiller] create draft failed: %s", exc)
            return None
