"""Diagnostic Chat Agent — enriches chat with knowledge search and log analysis context."""

from __future__ import annotations

from typing import Any, Dict, Generator, List, Optional

from sqlalchemy.orm import Session

from app.services.knowledge.knowledge_service import KnowledgeService


class DiagnosticChatAgent:
    """Wraps chat flow with diagnostic context injection.

    Before each LLM call, automatically:
    1. Searches knowledge base for docs matching the user's query
    2. Injects relevant knowledge as system context
    3. If session has log analysis data, injects that too

    This gives the LLM real-time access to the platform's knowledge and
    analysis results, enabling informed diagnostic responses.
    """

    SYSTEM_BASE = (
        "你是一个专业的设备日志诊断助手。"
        "请根据对话历史、知识库资料和分析结果，帮助用户诊断设备问题。"
        "使用 Markdown 格式回复，引用相关资料时注明来源。"
    )

    # 软引导：只在消息过于简略时追加提示，不阻断正常对话
    GUIDING_HINT = (
        "（如果用户描述不够具体，请在回答末尾用一两句引导用户补充设备型号、故障现象等关键信息。）"
    )

    def __init__(self, db: Session, provider_name: str = "mock"):
        self.db = db
        self.provider_name = provider_name
        self.knowledge = KnowledgeService(db)
        # Metadata for the UI; never inject this raw object into the model.
        self.references: List[Dict[str, Any]] = []

    @staticmethod
    def is_brief(user_message: str) -> bool:
        """判断用户输入是否非常简略（仅用于追加软引导提示）。"""
        msg = user_message.strip()
        if len(msg) <= 5:
            return True
        # 仅纯粹问候
        simple_patterns = ["你好", "在吗", "hello", "hi"]
        return any(msg.lower().startswith(p) for p in simple_patterns)

    def enrich_messages(
        self,
        session_id: int,
        user_message: str,
        existing_messages: List[Dict[str, str]],
        log_analysis: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """Build enriched messages with injected diagnostic context.

        始终让 LLM 自由回复；仅在用户输入极简时追加软引导提示。
        """
        # 1. Search knowledge base
        knowledge_context = self._search_knowledge(user_message)

        # 2. Build analysis context from log results
        analysis_context = self._build_analysis_context(log_analysis)

        # 3. Build enriched system prompt
        system_parts = [self.SYSTEM_BASE]

        if knowledge_context:
            system_parts.append(f"\n## 知识库相关资料\n\n{knowledge_context}")

        if analysis_context:
            system_parts.append(f"\n## 日志分析结果\n\n{analysis_context}")

        # 极简短消息追加软引导，不阻断正常对话
        if self.is_brief(user_message) and not log_analysis:
            system_parts.append(self.GUIDING_HINT)

        system_prompt = "\n".join(system_parts)

        enriched: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]
        for m in existing_messages:
            if m.get("role") != "system":
                enriched.append(m)

        return enriched

    def _search_knowledge(self, query: str) -> str:
        """Search knowledge base for matching docs. Returns formatted context or empty string."""
        if not query.strip():
            return ""

        try:
            result = self.knowledge.search(query, page_size=5)
            items = result.get("items", [])
            if not items:
                return ""

            lines = []
            self.references = []
            for i, item in enumerate(items):
                title = item.get("title", "Untitled")
                snippet = item.get("snippet", "")[:300]
                score = item.get("relevance_score", 0)
                if score > 0.1:  # Only include reasonably relevant results
                    lines.append(f"{i + 1}. **{title}** (相关度: {score:.0%})\n   {snippet}")
                    self.references.append({
                        "id": item.get("id"),
                        "title": title,
                        "source": item.get("source") or "知识库",
                        "excerpt": snippet,
                    })

            return "\n\n".join(lines) if lines else ""
        except Exception:
            return ""

    def _build_analysis_context(self, analysis: Optional[Dict[str, Any]]) -> str:
        """Format analysis results as context string."""
        if not analysis:
            return ""

        parts = []
        summary = analysis.get("summary", "")
        if summary:
            parts.append(f"**诊断摘要**: {summary}")

        root_cause = analysis.get("root_cause", "")
        if root_cause:
            parts.append(f"**根因分析**: {root_cause}")

        confidence = analysis.get("confidence", 0)
        parts.append(f"**置信度**: {confidence:.0%}")

        next_steps = analysis.get("next_steps", [])
        if next_steps:
            steps = "\n".join(f"- {s}" for s in next_steps)
            parts.append(f"**建议措施**:\n{steps}")

        return "\n".join(parts)
