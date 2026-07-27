"""Context window management — auto-summarize long conversations."""

from __future__ import annotations

from typing import Any, Dict, List

# Token 估算：中文平均 1.5 token/字，英文 0.25 token/word
MAX_CONTEXT_TOKENS = 8000  # 保守估计，为模型最大上下文的 50%
SUMMARY_TRIGGER_TOKENS = 6000  # 超过此值触发摘要


class ContextManager:
    """长对话上下文管理器 — 自动摘要压缩。

    策略：
    1. 保留系统提示词（始终）
    2. 保留最近 N 条消息（最新上下文）
    3. 将中间部分压缩为摘要（减少 token）
    """

    def __init__(self, max_tokens: int = MAX_CONTEXT_TOKENS):
        self.max_tokens = max_tokens
        self.summary_trigger = SUMMARY_TRIGGER_TOKENS

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
        # 估算 token 数
        total_tokens = self._estimate_tokens(messages)

        if total_tokens < self.summary_trigger:
            # 上下文未超限，直接返回
            return messages

        # 需要压缩
        return self._compress_messages(messages, system_prompt)

    def _compress_messages(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str | None = None,
    ) -> List[Dict[str, str]]:
        """压缩消息历史。

        策略：
        - 保留最近 8 条消息（4 轮对话）
        - 将前面的消息摘要为一条 assistant 消息
        """
        if len(messages) <= 8:
            return messages

        # 保留最近 8 条
        recent = messages[-8:]
        # 需要摘要的历史
        to_summarize = messages[:-8]

        # 生成摘要
        summary_text = self._generate_summary(to_summarize)

        # 插入摘要消息
        compressed = [
            {
                "role": "assistant",
                "content": (
                    "## 📝 对话历史摘要\n\n"
                    f"> 以下是前 {len(to_summarize)} 条消息的摘要，供参考：\n\n"
                    f"{summary_text}\n\n"
                    "---\n\n"
                    "*（以下是最近的对话）*"
                ),
            }
        ]
        compressed.extend(recent)

        return compressed

    def _generate_summary(self, messages: List[Dict[str, str]]) -> str:
        """生成对话摘要（简单实现，未调用 LLM）。

        TODO: 可选优化 — 调用 LLM 生成更智能的摘要
        """
        lines: list[str] = []
        user_count = 0
        assistant_count = 0

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")[:100]  # 截取前 100 字符

            if role == "user":
                user_count += 1
                lines.append(f"- 用户问题 {user_count}: {content}...")
            elif role == "assistant":
                assistant_count += 1
                lines.append(f"- AI 回复 {assistant_count}: {content}...")

        return "\n".join(lines) if lines else "（无对话历史）"

    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """粗略估算消息列表的 token 数。

        估算规则：
        - 中文：1.5 token/字
        - 英文/数字：0.25 token/word
        - JSON 结构开销：每条消息 +10 token
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            # 中文字符数
            chinese = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
            # 非中文字符数（英文单词估算）
            non_chinese = len(content) - chinese
            words = non_chinese / 5  # 粗略估算单词数

            total += int(chinese * 1.5 + words * 0.25 + 10)

        return total

    @staticmethod
    def should_compress(messages: List[Dict[str, str]]) -> bool:
        """判断是否需要压缩上下文。"""
        return len(messages) > 20  # 超过 20 条消息（10 轮对话）触发
