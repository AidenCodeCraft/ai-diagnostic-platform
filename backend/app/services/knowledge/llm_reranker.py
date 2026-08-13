"""LLM-as-Reranker — 利用 DeepSeek 推理能力辅助精排。

使用场景：
  - Cross-Encoder 最高分 < 阈值（如 0.3），分数区分度不足
  - 候选文档语义相近，Cross-Encoder 难以区分
  - 作为 Cross-Encoder 的补充，而非替代

设计原则：
  - 仅在 Cross-Encoder 结果置信度低时触发（延迟敏感场景不调用）
  - 设置 3s 超时，失败静默回退到 Cross-Encoder 结果
  - 不增加常态请求的延迟
"""

from __future__ import annotations

import json
import logging
import time
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# LLM Reranker 的默认超时（秒）
DEFAULT_TIMEOUT = 3.0
# 触发 LLM Reranker 的 Cross-Encoder 分数阈值
DEFAULT_CONFIDENCE_THRESHOLD = 0.3


class LLMReranker:
    """LLM 辅助重排序器 — Cross-Encoder 的智能补充。

    使用 DeepSeek 的推理能力对候选文档进行语义级别的重排序，
    仅在 Cross-Encoder 分数区分度不足时触发。

    Usage:
        llm_reranker = LLMReranker(model="deepseek-chat")
        reranked = llm_reranker.rerank(
            query="设备黑屏怎么办",
            documents=[(idx, "文档内容..."), ...],
            cross_encoder_scores=[0.25, 0.22, 0.21, ...],
        )
    """

    def __init__(
        self,
        model: str = "deepseek-chat",
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.model = model
        self.confidence_threshold = confidence_threshold
        self.timeout = timeout

    def should_trigger(self, cross_encoder_scores: List[float]) -> bool:
        """判断是否需要触发 LLM 辅助重排序。

        触发条件：最高分 < 阈值（分数区分度不足）。

        Args:
            cross_encoder_scores: Cross-Encoder 的原始分数列表

        Returns:
            是否需要触发 LLM 重排序
        """
        if not cross_encoder_scores:
            return False
        return max(cross_encoder_scores) < self.confidence_threshold

    def rerank(
        self,
        query: str,
        documents: List[Tuple[int, str]],
        cross_encoder_scores: List[float],
        top_k: int = 5,
    ) -> Optional[List[Tuple[int, float]]]:
        """LLM 辅助重排序。

        Args:
            query: 用户查询
            documents: [(原始索引, 文档文本), ...]
            cross_encoder_scores: Cross-Encoder 的原始分数（用于日志对比）
            top_k: 返回前 K 个结果

        Returns:
            [(原始索引, LLM 相关性分数), ...] 或 None（失败时回退）
        """
        if not self.should_trigger(cross_encoder_scores):
            logger.debug(
                "[LLMReranker] CE max=%.3f >= threshold=%.3f, skipping LLM rerank",
                max(cross_encoder_scores) if cross_encoder_scores else 0,
                self.confidence_threshold,
            )
            return None

        if not documents:
            return None

        start = time.time()
        try:
            result = self._call_llm_rerank(query, documents, top_k)
            elapsed = time.time() - start
            logger.info(
                "[LLMReranker] LLM rerank done in %.1fs, "
                "CE max=%.3f → LLM top=%.3f",
                elapsed,
                max(cross_encoder_scores) if cross_encoder_scores else 0,
                result[0][1] if result else 0,
            )
            return result
        except Exception as e:
            logger.warning(
                "[LLMReranker] LLM rerank failed (%.1fs): %s, falling back to CE",
                time.time() - start, e,
            )
            return None

    def _call_llm_rerank(
        self,
        query: str,
        documents: List[Tuple[int, str]],
        top_k: int,
    ) -> List[Tuple[int, float]]:
        """调用 LLM 进行语义重排序。

        Prompt 策略：
          - 要求 LLM 按相关性排序，输出 JSON
          - 每条文档限制摘要长度（避免 token 超限）
          - 设置低 temperature 保证排序稳定性
        """
        import concurrent.futures

        # 构建 prompt
        doc_lines = []
        for idx, (orig_idx, text) in enumerate(documents[:15]):  # 最多 15 条候选
            # 截取文档摘要（前 300 字符）
            snippet = text[:300].replace("\n", " ")
            doc_lines.append(f"[{idx}] {snippet}")

        prompt = (
            "你是一个文档相关性排序助手。请根据用户问题的语义意图，"
            "对以下候选文档按相关性从高到低排序。\n\n"
            f"用户问题: {query}\n\n"
            "候选文档:\n" + "\n".join(doc_lines) + "\n\n"
            f"请返回 JSON 格式的排序结果（top {top_k}）:\n"
            '{"ranked": [{"index": 0, "score": 0.95, "reason": "直接相关"}, ...]}\n\n'
            "注意：score 为 0.0~1.0 的相关性分数，reason 为简短理由（不超过15字）。"
        )

        # 使用线程池设置超时
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._do_llm_call, prompt)
            try:
                response = future.result(timeout=self.timeout)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(
                    f"LLM rerank timed out after {self.timeout}s"
                )

        return self._parse_llm_response(response, documents, top_k)

    def _do_llm_call(self, prompt: str) -> str:
        """执行实际的 LLM 调用。"""
        from app.services.knowledge.provider_registry import ProviderRegistry

        provider = ProviderRegistry().get_provider(self.model)
        return provider.chat([
            {
                "role": "system",
                "content": (
                    "你是一个精确的文档排序助手。只返回 JSON，不要解释。"
                ),
            },
            {"role": "user", "content": prompt},
        ])

    @staticmethod
    def _parse_llm_response(
        response: str,
        documents: List[Tuple[int, str]],
        top_k: int,
    ) -> List[Tuple[int, float]]:
        """解析 LLM 重排序响应。

        Args:
            response: LLM 原始响应文本
            documents: 原始文档列表 [(原始索引, 文本), ...]
            top_k: 返回前 K 个

        Returns:
            [(原始索引, 相关性分数), ...]
        """
        # 提取 JSON
        response = response.strip()
        # 移除 markdown fences
        if response.startswith("```"):
            lines = response.split("\n")
            if len(lines) >= 3 and lines[-1].strip() == "```":
                response = "\n".join(lines[1:-1])
            else:
                response = "\n".join(lines[1:])

        try:
            data = json.loads(response)
            ranked = data.get("ranked", [])
        except json.JSONDecodeError:
            logger.warning(
                "[LLMReranker] Failed to parse LLM JSON response: %.100s",
                response,
            )
            return []

        results = []
        for item in ranked[:top_k]:
            llm_idx = item.get("index", -1)
            score = item.get("score", 0.5)
            if 0 <= llm_idx < len(documents):
                orig_idx = documents[llm_idx][0]
                results.append((orig_idx, float(score)))

        return results
