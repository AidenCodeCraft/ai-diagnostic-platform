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

    # 当用户输入信息不足时，提供启发式引导询问
    GUIDING_PROMPT = (
        "用户当前的描述信息不够具体。请用友好的语气引导用户补充以下关键信息：\n"
        "1. 设备类型和型号（如嵌入式设备、Linux 服务器、MCU 等）\n"
        "2. 具体的故障现象（什么时候发生、频率、是否有规律）\n"
        "3. 是否有日志文件可以上传分析\n"
        "4. 最近是否有硬件或软件变更\n\n"
        "根据用户已经提供的信息，只询问缺失的部分。用 Markdown 格式回复。"
    )

    def __init__(self, db: Session, provider_name: str = "mock"):
        self.db = db
        self.provider_name = provider_name
        self.knowledge = KnowledgeService(db)
        # Metadata for the UI; never inject this raw object into the model.
        self.references: List[Dict[str, Any]] = []

    @staticmethod
    def needs_guiding(user_message: str) -> bool:
        """判断用户输入是否过于简略，需要引导提问。"""
        msg = user_message.strip()
        if len(msg) < 15:
            return True
        # 仅问候或极简描述
        simple_patterns = ["你好", "在吗", "hello", "hi", "帮助", "help"]
        if any(msg.lower().startswith(p) for p in simple_patterns):
            return True
        # 已有具体关键词则不需要引导
        detail_keywords = ["错误", "日志", "error", "log", "故障", "重启", "crash",
                          "超时", "timeout", "panic", "failed", "失败", "黑屏",
                          "kernel", "驱动", "driver", "死机", "异常"]
        return not any(kw in msg.lower() for kw in detail_keywords)

    def enrich_messages(
        self,
        session_id: int,
        user_message: str,
        existing_messages: List[Dict[str, str]],
        log_analysis: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """Build enriched messages with injected diagnostic context."""
        # 1. 信息不足时注入引导提示
        if self.needs_guiding(user_message) and not log_analysis:
            return self._build_guiding_messages(existing_messages)

        # 2. Search knowledge base
        knowledge_context = self._search_knowledge(user_message)

        # 3. Build analysis context from log results
        analysis_context = self._build_analysis_context(log_analysis)

        # 4. Build enriched system prompt
        system_parts = [self.SYSTEM_BASE]

        if knowledge_context:
            system_parts.append(f"\n## 知识库相关资料\n\n{knowledge_context}")

        if analysis_context:
            system_parts.append(f"\n## 日志分析结果\n\n{analysis_context}")

        system_prompt = "\n".join(system_parts)

        enriched: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]
        for m in existing_messages:
            if m.get("role") != "system":
                enriched.append(m)

        return enriched

    def _build_guiding_messages(
        self, existing_messages: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """当用户信息不足时，构建引导提问的消息列表。"""
        guiding_system = self.SYSTEM_BASE + "\n\n" + self.GUIDING_PROMPT
        return [
            {"role": "system", "content": guiding_system}
        ] + [m for m in existing_messages if m.get("role") != "system"]

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
