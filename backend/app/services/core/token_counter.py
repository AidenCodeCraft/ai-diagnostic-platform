"""模型感知的 Token 计数器 — 精确替代启发式估算。

支持:
  - DeepSeek 系列: cl100k_base (与 GPT-4 兼容)
  - Qwen 系列: qwen 专用 tokenizer
  - 回退: 启发式估算（兼容旧行为）

Usage:
    counter = TokenCounter()
    tokens = counter.count("设备黑屏怎么办？", model="deepseek-chat")
    budget = counter.get_context_budget("deepseek-v4", ratio=0.7)
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 模型 → tiktoken encoding 映射
# ---------------------------------------------------------------------------
MODEL_ENCODING_MAP: Dict[str, str] = {
    "deepseek-chat":      "cl100k_base",
    "deepseek-reasoner":  "cl100k_base",
    "deepseek-v4":        "cl100k_base",
    "deepseek-v4-flash":  "cl100k_base",
    "gpt-4o":             "o200k_base",
    "gpt-4":              "cl100k_base",
    "gpt-3.5-turbo":      "cl100k_base",
}

# tiktoken 不可用时的回退编码
FALLBACK_ENCODING = "cl100k_base"

# ---------------------------------------------------------------------------
# 各模型的最大上下文窗口（tokens）
# ---------------------------------------------------------------------------
MODEL_CONTEXT_LIMITS: Dict[str, int] = {
    "deepseek-chat":      64_000,
    "deepseek-reasoner":  64_000,
    "deepseek-v4":        1_000_000,
    "deepseek-v4-flash":  1_000_000,
    "gpt-4o":             128_000,
    "gpt-4":              8_192,
    "gpt-3.5-turbo":      16_385,
    "qwen-max":           32_000,
    "qwen-plus":          131_072,
    "default":            32_000,
}

# ---------------------------------------------------------------------------
# tiktoken 可用性检测
# ---------------------------------------------------------------------------
_TIKTOKEN_AVAILABLE = False
try:
    import tiktoken  # noqa: F401
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    logger.warning(
        "tiktoken not installed, falling back to heuristic estimation. "
        "Install with: pip install tiktoken"
    )


class TokenCounter:
    """模型感知的精确 Token 计数器。

    优先级:
      1. tiktoken 精确计数（如果已安装）
      2. 启发式估算（回退，兼容旧行为）

    Usage:
        counter = TokenCounter()
        tokens = counter.count("设备黑屏怎么办？", model="deepseek-chat")
        budget = counter.get_context_budget("deepseek-v4", ratio=0.7)
    """

    def __init__(self) -> None:
        self._encoders: Dict[str, object] = {}
        self._tiktoken_available = _TIKTOKEN_AVAILABLE

    # ------------------------------------------------------------------
    # Token 计数
    # ------------------------------------------------------------------

    def count(self, text: str, model: str = "default") -> int:
        """精确计算文本的 token 数。

        Args:
            text: 输入文本
            model: 模型名称（用于选择正确的 tokenizer）

        Returns:
            token 数量
        """
        if not text:
            return 0

        if self._tiktoken_available:
            return self._count_tiktoken(text, model)
        else:
            return self._count_heuristic(text)

    def count_messages(
        self,
        messages: List[Dict[str, str]],
        model: str = "default",
    ) -> int:
        """计算消息列表的总 token 数（含角色标记开销）。

        参照 OpenAI 的 token 计数规则:
          - 每条消息: +4 tokens (角色标记)
          - 整个列表: +2 tokens (开始/结束标记)
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += self.count(content, model)
            total += 4  # 角色标记开销
        total += 2  # 列表开始/结束
        return total

    # ------------------------------------------------------------------
    # 上下文预算
    # ------------------------------------------------------------------

    def get_context_limit(self, model: str) -> int:
        """获取模型的上下文窗口上限。

        Args:
            model: 模型名称

        Returns:
            上下文窗口上限（tokens）
        """
        # 精确匹配
        if model in MODEL_CONTEXT_LIMITS:
            return MODEL_CONTEXT_LIMITS[model]

        # 前缀匹配（如 deepseek-v4-xxx → deepseek-v4）
        for prefix, limit in MODEL_CONTEXT_LIMITS.items():
            if model.startswith(prefix):
                return limit

        return MODEL_CONTEXT_LIMITS["default"]

    def get_chat_budget(
        self,
        model: str,
        ratio: float = 0.6,
        min_budget: int = 4_000,
    ) -> int:
        """计算对话上下文的 token 预算。

        Args:
            model: 模型名称
            ratio: 占用上下文窗口的比例（默认 60%）
            min_budget: 最小预算（防止小窗口模型过于受限）

        Returns:
            token 预算
        """
        limit = self.get_context_limit(model)
        budget = int(limit * ratio)
        return max(budget, min_budget)

    def get_rag_budget(
        self,
        model: str,
        ratio: float = 0.7,
        overhead: int = 4_000,
    ) -> int:
        """计算 RAG 检索上下文的 token 预算。

        Args:
            model: 模型名称
            ratio: 占用上下文窗口的比例（默认 70%）
            overhead: 预留给 system prompt + 用户指令的 token

        Returns:
            RAG 检索 token 预算
        """
        limit = self.get_context_limit(model)
        budget = int(limit * ratio)
        # 扣除固定开销（system prompt ~2000 + 用户指令 ~2000）
        return max(budget - overhead, 0)

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    def _count_tiktoken(self, text: str, model: str) -> int:
        """使用 tiktoken 精确计数。"""
        encoding_name = self._get_encoding_name(model)
        encoder = self._get_encoder(encoding_name)
        return len(encoder.encode(text))

    @lru_cache(maxsize=8)
    def _get_encoder(self, encoding_name: str):
        """缓存 encoder 实例，避免重复创建。"""
        import tiktoken
        try:
            return tiktoken.get_encoding(encoding_name)
        except KeyError:
            logger.warning(
                "Encoding '%s' not found, using '%s'",
                encoding_name, FALLBACK_ENCODING,
            )
            return tiktoken.get_encoding(FALLBACK_ENCODING)

    @staticmethod
    def _get_encoding_name(model: str) -> str:
        """根据模型名获取对应的 encoding 名称。"""
        if model in MODEL_ENCODING_MAP:
            return MODEL_ENCODING_MAP[model]
        for prefix, encoding in MODEL_ENCODING_MAP.items():
            if model.startswith(prefix):
                return encoding
        return FALLBACK_ENCODING

    @staticmethod
    def _count_heuristic(text: str) -> int:
        """启发式估算（tiktoken 不可用时的回退）。

        规则（与旧 ContextManager 一致）:
          - 中文: 1.5 token/字
          - 英文/数字: 0.25 token/word
          - 结构开销: +10 token
        """
        chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        non_chinese = len(text) - chinese
        words = non_chinese / 5
        return int(chinese * 1.5 + words * 0.25 + 10)


# ---------------------------------------------------------------------------
# 模块级单例
# ---------------------------------------------------------------------------

_counter: Optional[TokenCounter] = None


def get_token_counter() -> TokenCounter:
    """获取 TokenCounter 全局单例。"""
    global _counter
    if _counter is None:
        _counter = TokenCounter()
    return _counter
