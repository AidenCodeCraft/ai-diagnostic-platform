"""Context window management — auto-summarize long conversations.

v2: 模型感知的动态上下文预算 + LLM 智能摘要。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 回退默认值（当无法获取模型上下文时使用）
FALLBACK_MAX_TOKENS = 8000
FALLBACK_SUMMARY_TRIGGER = 6000
# 压缩时保留的最近消息数
KEEP_RECENT_COUNT = 8
# 消息数触发阈值
MESSAGE_COUNT_THRESHOLD = 20


class ContextManager:
    """长对话上下文管理器 — 模型感知 + 自动摘要压缩。

    策略（v2 增强）：
    1. 根据模型动态计算上下文预算（不再硬编码 8000）
    2. 保留系统提示词（始终）
    3. 保留最近 N 条消息（最新上下文）
    4. 将中间部分通过 LLM 压缩为智能摘要

    Usage:
        mgr = ContextManager(model="deepseek-v4")
        compressed = mgr.manage_context(messages)
    """

    def __init__(
        self,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        summary_trigger: Optional[int] = None,
    ):
        """初始化上下文管理器。

        Args:
            model: 模型名称（用于动态计算上下文预算）
            max_tokens: 手动覆盖最大 token 数
            summary_trigger: 手动覆盖摘要触发阈值
        """
        self.model = model
        self._max_tokens = max_tokens
        self._summary_trigger = summary_trigger

    @property
    def max_tokens(self) -> int:
        """获取上下文 token 预算（优先手动覆盖 → 模型感知 → 回退默认值）。"""
        if self._max_tokens is not None:
            return self._max_tokens
        if self.model:
            try:
                from app.services.core.token_counter import get_token_counter
                from app.services.core.config import DEFAULT_CONFIG
                return get_token_counter().get_chat_budget(
                    self.model,
                    ratio=DEFAULT_CONFIG.context.chat_budget_ratio,
                    min_budget=DEFAULT_CONFIG.context.chat_min_budget,
                )
            except Exception as e:
                logger.debug("Failed to get model-aware budget: %s", e)
        return FALLBACK_MAX_TOKENS

    @property
    def summary_trigger(self) -> int:
        """获取摘要触发阈值（优先手动覆盖 → 80% 预算 → 回退默认值）。"""
        if self._summary_trigger is not None:
            return self._summary_trigger
        return int(self.max_tokens * 0.75)

    def manage_context(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str | None = None,
    ) -> List[Dict[str, str]]:
        """管理对话上下文，必要时进行摘要压缩。

        Args:
            messages: 完整对话历史（不含 system）
            system_prompt: 系统提示词（可选）

        Returns:
            压缩后的消息列表
        """
        # 使用 TokenCounter 精确计数
        total_tokens = self._count_tokens(messages)

        logger.debug(
            "[ContextManager] tokens=%d trigger=%d max=%d model=%s",
            total_tokens, self.summary_trigger, self.max_tokens, self.model,
        )

        if total_tokens < self.summary_trigger:
            return messages

        return self._compress_messages(messages, system_prompt)

    def _compress_messages(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str | None = None,
    ) -> List[Dict[str, str]]:
        """压缩消息历史。

        策略：
        - 保留最近 N 条消息
        - 将前面的消息通过 LLM 摘要为一条 assistant 消息
        """
        if len(messages) <= KEEP_RECENT_COUNT:
            return messages

        recent = messages[-KEEP_RECENT_COUNT:]
        to_summarize = messages[:-KEEP_RECENT_COUNT]

        summary_text = self._generate_summary(to_summarize)

        compressed = [
            {
                "role": "assistant",
                "content": (
                    "## 对话历史摘要\n\n"
                    f"> 以下是前 {len(to_summarize)} 条消息的摘要，供参考：\n\n"
                    f"{summary_text}\n\n"
                    "---\n\n"
                    "*（以下是最近的对话）*"
                ),
            }
        ]
        compressed.extend(recent)

        logger.info(
            "[ContextManager] Compressed %d messages → summary + %d recent",
            len(to_summarize), len(recent),
        )
        return compressed

    def _generate_summary(self, messages: List[Dict[str, str]]) -> str:
        """生成对话摘要。

        优先级：
        1. LLM 智能摘要（如果 Provider 可用）
        2. 规则回退（LLM 不可用时）
        """
        # 尝试 LLM 摘要
        llm_summary = self._try_llm_summary(messages)
        if llm_summary:
            return llm_summary

        # 回退：规则摘要
        return self._rule_based_summary(messages)

    def _try_llm_summary(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """尝试使用 LLM 生成智能摘要。

        Returns:
            摘要文本，失败时返回 None
        """
        try:
            from app.services.knowledge.provider_registry import ProviderRegistry

            # 构建摘要 prompt
            conversation_text = "\n".join(
                f"[{m.get('role', 'unknown')}]: {m.get('content', '')[:300]}"
                for m in messages
            )

            prompt = (
                "请将以下对话历史压缩为简洁的摘要（200字以内），"
                "重点保留：用户提出的技术问题、已确认的事实、待解决的问题。\n\n"
                f"对话历史:\n{conversation_text}"
            )

            provider = ProviderRegistry().get_provider(
                self.model or "deepseek-chat"
            )
            summary = provider.chat(
                [{"role": "user", "content": prompt}],
                max_tokens=300,
            )

            if summary and len(summary.strip()) > 10:
                return summary.strip()

        except Exception as e:
            logger.debug("[ContextManager] LLM summary failed, using rule-based: %s", e)

        return None

    def _rule_based_summary(self, messages: List[Dict[str, str]]) -> str:
        """规则回退摘要（保留旧行为）。"""
        lines: list[str] = []
        user_count = 0
        assistant_count = 0

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")[:100]

            if role == "user":
                user_count += 1
                lines.append(f"- 用户问题 {user_count}: {content}...")
            elif role == "assistant":
                assistant_count += 1
                lines.append(f"- AI 回复 {assistant_count}: {content}...")

        return "\n".join(lines) if lines else "（无对话历史）"

    def _count_tokens(self, messages: List[Dict[str, str]]) -> int:
        """使用 TokenCounter 精确计数（回退到启发式）。"""
        try:
            from app.services.core.token_counter import get_token_counter
            return get_token_counter().count_messages(
                messages, model=self.model or "default"
            )
        except Exception:
            # 终极回退：旧启发式算法
            return self._estimate_tokens(messages)

    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """启发式 token 估算（旧行为，作为终极回退）。

        估算规则：
        - 中文：1.5 token/字
        - 英文/数字：0.25 token/word
        - JSON 结构开销：每条消息 +10 token
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            chinese = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
            non_chinese = len(content) - chinese
            words = non_chinese / 5
            total += int(chinese * 1.5 + words * 0.25 + 10)
        return total

    @staticmethod
    def should_compress(messages: List[Dict[str, str]]) -> bool:
        """判断是否需要压缩上下文（基于消息数量）。"""
        return len(messages) > MESSAGE_COUNT_THRESHOLD
