"""DeepSeek 推理增强 — 问题分析与子问题分解。

设计原则：
  1. 规则评分始终作为第一道快速路径（延迟 <1ms）
  2. 仅当规则评分置信度低时，异步触发 DeepSeek 深度分析
  3. DeepSeek 分析设置 3s 超时，失败静默回退到规则结果
  4. DeepSeek 分析结果会合并到规则结果中（增强而非替代）

Usage:
    analyzer = DeepSeekQuestionAnalyzer(model="deepseek-chat")
    enhanced = analyzer.analyze(
        user_input="设备反复重启，日志里有kernel panic",
        rule_analysis={"is_diagnostic": True, "score": 4, "confidence": 0.5},
    )
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置常量
# ---------------------------------------------------------------------------

DEEPSEEK_ANALYSIS_TIMEOUT = 3.0
CONFIDENCE_THRESHOLD = 0.6  # 规则评分置信度低于此值触发 LLM 分析


class DeepSeekQuestionAnalyzer:
    """使用 DeepSeek 推理能力增强问题分析。

    增强规则分析的以下维度：
      - 技术领域和组件识别（domains）
      - 子问题分解（sub_questions）
      - 问题紧急程度（urgency）
      - 整体置信度提升（confidence）
    """

    def __init__(
        self,
        model: str = "deepseek-chat",
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
        timeout: float = DEEPSEEK_ANALYSIS_TIMEOUT,
    ) -> None:
        self.model = model
        self.confidence_threshold = confidence_threshold
        self.timeout = timeout

    def should_enhance(self, rule_analysis: Dict[str, Any]) -> bool:
        """判断是否需要 DeepSeek 增强分析。

        条件：
          - 规则判定为诊断问题
          - 规则评分置信度 < 阈值

        Args:
            rule_analysis: 规则分析结果

        Returns:
            是否需要增强
        """
        if not rule_analysis.get("is_diagnostic"):
            return False

        confidence = rule_analysis.get("confidence", 1.0)
        return confidence < self.confidence_threshold

    def analyze(
        self,
        user_input: str,
        rule_analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """DeepSeek 增强分析。

        Args:
            user_input: 用户原始输入
            rule_analysis: 规则分析结果

        Returns:
            增强后的分析结果（合并了规则分析和 LLM 分析）
        """
        if not self.should_enhance(rule_analysis):
            return rule_analysis

        start = time.time()
        try:
            llm_result = self._call_deepseek_analyze(user_input)
            elapsed = time.time() - start
            logger.info(
                "[DeepSeekAnalysis] Enhanced in %.1fs, "
                "confidence %.2f → %.2f, domains=%s",
                elapsed,
                rule_analysis.get("confidence", 0),
                llm_result.get("confidence", 0),
                llm_result.get("domains", []),
            )
            return self._merge_results(rule_analysis, llm_result)
        except Exception as e:
            logger.debug(
                "[DeepSeekAnalysis] Failed (%.1fs): %s, keeping rule result",
                time.time() - start, e,
            )
            return rule_analysis

    def _call_deepseek_analyze(self, user_input: str) -> Dict[str, Any]:
        """调用 DeepSeek 进行深度问题分析。"""
        import concurrent.futures

        prompt = (
            "你是一个诊断问题分析助手。请分析以下用户输入，判断：\n"
            "1. 是否为技术诊断类问题\n"
            "2. 涉及的技术领域和组件\n"
            "3. 问题是否可以拆分为子问题\n"
            "4. 问题的紧急程度\n\n"
            f"用户输入: {user_input}\n\n"
            "请以 JSON 格式返回（不要包含 markdown 代码块标记）:\n"
            '{"is_diagnostic": true/false, '
            '"domains": ["kernel", "hardware"], '
            '"sub_questions": ["子问题1", "子问题2"], '
            '"urgency": "high"/"medium"/"low", '
            '"confidence": 0.0-1.0, '
            '"reasoning": "简要推理过程"}'
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._do_llm_call, prompt)
            try:
                response = future.result(timeout=self.timeout)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(
                    f"DeepSeek analysis timed out after {self.timeout}s"
                )

        return self._parse_response(response)

    def _do_llm_call(self, prompt: str) -> str:
        """执行实际的 LLM 调用。"""
        from app.services.knowledge.provider_registry import ProviderRegistry

        provider = ProviderRegistry().get_provider(self.model)
        return provider.chat([
            {
                "role": "system",
                "content": "你是一个精确的诊断问题分析助手。只返回 JSON，不要解释。",
            },
            {"role": "user", "content": prompt},
        ])

    @staticmethod
    def _parse_response(response: str) -> Dict[str, Any]:
        """解析 LLM 分析响应。

        Args:
            response: LLM 原始响应文本

        Returns:
            解析后的分析结果
        """
        response = response.strip()

        # 移除 markdown fences
        if response.startswith("```"):
            lines = response.split("\n")
            if len(lines) >= 3 and lines[-1].strip() == "```":
                response = "\n".join(lines[1:-1])
            else:
                response = "\n".join(lines[1:])

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning(
                "[DeepSeekAnalysis] Failed to parse LLM JSON: %.100s",
                response,
            )
            return {
                "is_diagnostic": True,
                "confidence": 0.5,
                "parse_error": True,
            }

    @staticmethod
    def _merge_results(
        rule: Dict[str, Any],
        llm: Dict[str, Any],
    ) -> Dict[str, Any]:
        """合并规则分析和 LLM 分析结果。

        合并策略：
          - is_diagnostic: 规则和 LLM 任意一个为 True 则 True
          - topics: 合并去重
          - sub_questions: LLM 分解优先，规则作为补充
          - confidence: 取 LLM 置信度（通常更准确）
          - 保留规则分析的所有原始字段

        Args:
            rule: 规则分析结果
            llm: LLM 分析结果

        Returns:
            合并后的分析结果
        """
        merged = dict(rule)  # 保留规则分析的原始字段

        # LLM 增强字段
        merged["llm_enhanced"] = True
        merged["llm_is_diagnostic"] = llm.get("is_diagnostic", False)
        merged["llm_domains"] = llm.get("domains", [])
        merged["llm_urgency"] = llm.get("urgency", "medium")
        merged["llm_confidence"] = llm.get("confidence", 0.5)
        merged["llm_reasoning"] = llm.get("reasoning", "")

        # 合并 topics（规则提取的中文词组 + LLM 识别的技术领域）
        rule_topics = set(rule.get("topics", []))
        llm_domains = set(llm.get("domains", []))
        merged["topics"] = list(rule_topics | llm_domains)[:12]

        # LLM 子问题优先，规则分解作为补充
        llm_subs = llm.get("sub_questions", [])
        rule_subs = rule.get("sub_questions", [])
        # 去重合并
        seen = set()
        merged_subs = []
        for sub in llm_subs + rule_subs:
            if sub not in seen:
                seen.add(sub)
                merged_subs.append(sub)
        merged["sub_questions"] = merged_subs[:5]

        # 置信度更新：取两者中较高的
        llm_conf = llm.get("confidence", 0)
        rule_conf = rule.get("confidence", 0)
        merged["confidence"] = max(rule_conf, llm_conf)

        return merged
