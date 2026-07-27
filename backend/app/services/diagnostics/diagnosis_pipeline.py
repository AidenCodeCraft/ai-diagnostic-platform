"""Diagnosis Pipeline — 标准化诊断流水线 + RAG 边界约束。

完整链路：
  Stage 1: 日志解析 → 结构化事件
  Stage 2: 日志裁剪 → 基于错误事件精准提取关键片段
  Stage 3: 规则引擎 → 确定性模式匹配
  Stage 4: RAG 知识检索 → 私域知识库强制检索
  Stage 5: 构建精确 Prompt → 用户问题 + 裁剪日志 + 规则 + 知识（标记来源）
  Stage 6: Agent 综合分析 → LLM 合成诊断报告（严格来源标注）

RAG 约束：
  - 知识库内容标记为「唯一外部参考」，LLM 不得引用知识库外的信息
  - 日志分析 + 规则引擎结果标记为「本地分析」，LLM 可基于此推理
"""

from __future__ import annotations

import json
import re as _re_module
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.services.knowledge.knowledge_service import KnowledgeService
from app.services.infrastructure.llm_service import LLMService
from app.services.diagnostics.parser_service import LogParserService
from app.services.system.rule_engine import RuleEngine

logger = get_logger(__name__)

# 错误行附近的上下文行数（前后各取多少行）
ERROR_CONTEXT_LINES = 8
# 裁剪后的日志最大字符数（防止 token 超限）
MAX_TRIMMED_LOG_CHARS = 4000
# 原始日志读取上限（用于回退）
MAX_RAW_LOG_BYTES = 20000


class DiagnosisPipeline:
    """标准化诊断流水线。

    Stage 1 → 日志裁剪：提取错误行及其上下文，禁止将完整原始日志直接喂给 AI
    Stage 2 → 规则引擎：确定性规则匹配已知错误模式
    Stage 3 → RAG 检索：基于用户问题 + 规则命中搜索知识库
    Stage 4 → AI 综合分析：LLM 综合前三阶段信息生成诊断报告
    """

    DIAGNOSIS_PROMPT = (
        "你是一名资深的嵌入式系统与设备诊断工程师。"
        "请根据以下信息进行综合分析，给出准确的诊断结果。\n\n"
        "## 数据来源与约束\n"
        "1. 【日志分析结果】【规则引擎结果】是本次诊断的本地分析数据，你可基于此自由推理。\n"
        "2. 【知识库相关案例】是外部参考，不得编造知识库未提及的信息；如与日志分析冲突，以日志为准。\n"
        "3. 输出必须使用中文，且为合法的 JSON 格式（不要用 markdown 代码块包裹）。\n"
        "4. 置信度要考虑规则引擎匹配程度、知识库相关度和错误事件严重性。\n"
        "5. 如果用户提出了具体问题，请围绕用户问题进行针对性分析。\n\n"
        "## 输入信息\n\n"
    )

    def __init__(self, db: Session, model: Optional[str] = None):
        self.db = db
        self.model = model
        self.parser = LogParserService()
        self.rule_engine = RuleEngine()
        self.knowledge = KnowledgeService(db)

    # ==================================================================
    # Public API
    # ==================================================================

    def run(self, file_path: str, user_query: str = "") -> Dict[str, Any]:
        """执行标准化诊断流水线。

        Returns:
            dict: summary, root_cause, confidence, next_steps,
                  rule_hits, knowledge_hits, event_count, error_count,
                  trimmed_log (裁剪后的日志), pipeline_stages (阶段信息)
        """
        filename = Path(file_path).name
        logger.info(
            "[Pipeline] Stage 0 — 开始: file=%s query=%s",
            filename, user_query[:80] if user_query else "(无)",
        )

        # ═══════════════════════════════════════════════════════════
        # Stage 1: 日志解析 → 结构化事件
        # ═══════════════════════════════════════════════════════════
        logger.info("[Pipeline] Stage 1 — 日志解析")
        raw_events = self.parser.parse_structured(file_path)
        events = [e.to_dict() for e in raw_events]
        error_events = [e for e in events if e.get("is_error")]
        logger.info(
            "[Pipeline] Stage 1 完成: 总事件=%d 错误事件=%d",
            len(events), len(error_events),
        )

        # ═══════════════════════════════════════════════════════════
        # Stage 2: 日志智能裁剪 — 提取关键错误片段
        # ═══════════════════════════════════════════════════════════
        logger.info("[Pipeline] Stage 2 — 日志裁剪")
        trimmed_log = self._trim_log(file_path, error_events, user_query)
        logger.info(
            "[Pipeline] Stage 2 完成: 裁剪后 %d 字符 (原始上限 %d 字节)",
            len(trimmed_log), MAX_RAW_LOG_BYTES,
        )

        # ═══════════════════════════════════════════════════════════
        # Stage 3: 规则引擎 — 确定性模式匹配
        # ═══════════════════════════════════════════════════════════
        logger.info("[Pipeline] Stage 3 — 规则引擎")
        rule_suggestions = self.rule_engine.generate_suggestions(raw_events)  # type: ignore[arg-type]
        rule_summary = self._format_rule_results(rule_suggestions)
        logger.info("[Pipeline] Stage 3 完成: %d 条规则命中", len(rule_suggestions))

        # ═══════════════════════════════════════════════════════════
        # Stage 4: RAG 知识检索 — 向量搜索 + 关键词回退
        # ═══════════════════════════════════════════════════════════
        logger.info("[Pipeline] Stage 4 — RAG 知识检索")
        knowledge_results = self._search_knowledge(user_query, rule_suggestions, events)
        knowledge_summary = self._format_knowledge_results(knowledge_results)
        logger.info("[Pipeline] Stage 4 完成: %d 条知识命中", len(knowledge_results))

        # ═══════════════════════════════════════════════════════════
        # Stage 5: 构建精确 Prompt（只包含裁剪后的关键日志）
        # ═══════════════════════════════════════════════════════════
        prompt = self._build_prompt(
            events=events,
            error_events=error_events,
            rule_summary=rule_summary,
            knowledge_summary=knowledge_summary,
            trimmed_log=trimmed_log,
            user_query=user_query,
        )

        # ═══════════════════════════════════════════════════════════
        # Stage 6: Agent 综合分析 — LLM 合成诊断报告
        # ═══════════════════════════════════════════════════════════
        logger.info("[Pipeline] Stage 5 — Agent 综合分析 (模型: %s)", self.model)
        try:
            llm_result = LLMService(model=self.model).generate_summary(
                log_content=prompt, events=events
            )
            logger.info(
                "[Pipeline] Stage 5 完成: confidence=%.2f",
                llm_result.get("confidence", 0),
            )
        except Exception as exc:
            logger.warning(
                "[Pipeline] LLM 失败 — 回退到规则引擎: %s", exc,
            )
            return self._fallback_from_rules(events, rule_suggestions)

        # ═══════════════════════════════════════════════════════════
        # Stage 7: 结果规范化
        # ═══════════════════════════════════════════════════════════
        payload = self._normalize(llm_result)
        return {
            "summary": payload.get("summary", "分析完成") or "分析完成",
            "root_cause": payload.get("root_cause", "请查看规则引擎匹配结果") or "请查看规则引擎匹配结果",
            "confidence": float(payload.get("confidence", 0.5) or 0.5),
            "next_steps": self._normalize_list(payload.get("next_steps", [])),
            "rule_hits": len(rule_suggestions),
            "knowledge_hits": len(knowledge_results),
            "event_count": len(events),
            "error_count": len(error_events),
            "trimmed_log": trimmed_log,
            "pipeline_stages": {
                "parsed_events": len(events),
                "error_events": len(error_events),
                "rule_hits": len(rule_suggestions),
                "knowledge_hits": len(knowledge_results),
            },
        }

    # ==================================================================
    # Stage 2: 日志智能裁剪
    # ==================================================================

    def _trim_log(
        self, file_path: str, error_events: list, user_query: str,
    ) -> str:
        """智能日志裁剪：基于错误事件提取关键片段。

        策略：
        1. 定位所有错误行号
        2. 对每个错误，提取前后各 ERROR_CONTEXT_LINES 行
        3. 合并重叠区间
        4. 如果用户提到了特定关键词，额外提取相关行
        5. 控制总长度不超过 MAX_TRIMMED_LOG_CHARS
        """
        try:
            all_lines = Path(file_path).read_text(
                encoding="utf-8", errors="ignore",
            ).splitlines()
        except Exception:
            return "(无法读取日志文件)"

        if not error_events:
            # 无错误事件：返回日志的头部 + 尾部摘要
            head = all_lines[:20]
            tail = all_lines[-10:] if len(all_lines) > 30 else []
            return "\n".join(head + (["..."] if tail else []) + tail)

        # 收集所有错误行号
        error_lines: set[int] = set()
        for evt in error_events:
            line_no = evt.get("line_no", 0)
            if line_no > 0:
                error_lines.add(line_no)

        if not error_lines:
            head = all_lines[:30]
            return "\n".join(head)

        # 为每个错误行扩展上下文窗口
        total_lines = len(all_lines)
        windows: list[tuple[int, int]] = []
        for line_no in sorted(error_lines):
            start = max(0, line_no - ERROR_CONTEXT_LINES - 1)
            end = min(total_lines, line_no + ERROR_CONTEXT_LINES)
            windows.append((start, end))

        # 合并重叠窗口
        merged: list[tuple[int, int]] = []
        for start, end in windows:
            if merged and start <= merged[-1][1] + 2:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))

        # 提取片段
        fragments: list[str] = []
        prev_end = -1
        for start, end in merged:
            if prev_end >= 0:
                fragments.append(f"... (跳过 {start - prev_end} 行) ...")
            chunk = all_lines[start:end]
            fragments.extend(chunk)
            prev_end = end

        result = "\n".join(fragments)

        # 如果用户有具体关键词，尝试定位相关行
        if user_query:
            result = self._enrich_with_keyword_lines(
                result, all_lines, user_query, fragments,
            )

        # 最终长度限制
        if len(result) > MAX_TRIMMED_LOG_CHARS:
            result = result[:MAX_TRIMMED_LOG_CHARS] + (
                f"\n\n... (日志已裁剪，原始共 {total_lines} 行 "
                f"{len(error_events)} 个错误事件) ..."
            )

        return result

    def _enrich_with_keyword_lines(
        self, result: str, all_lines: list, user_query: str,
        existing_fragments: list,
    ) -> str:
        """如果用户问题中有特定关键词，追加相关行的上下文。"""
        # 提取用户问题中的中文/英文关键词（过滤通用词汇）
        stop_words = {"的", "是", "了", "在", "和", "有", "这个", "那个",
                       "什么", "怎么", "为什么", "如何", "帮我", "分析",
                       "一下", "这个", "问题", "the", "a", "an", "is",
                       "to", "of", "in", "for", "and"}
        # 用正则提取中文词（2+ 字）和英文词（3+ 字母）
        tokens: set[str] = set()
        for m in _re_module.finditer(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", user_query.lower()):
            token = m.group()
            if token not in stop_words:
                tokens.add(token)

        if not tokens:
            return result

        # 查找包含关键词的行号（排除已在 fragments 中的）
        extra_lines: list[str] = []
        for i, line in enumerate(all_lines):
            line_lower = line.lower()
            if any(t in line_lower or t.lower() in line_lower for t in tokens):
                extra_lines.append(f"[关键词命中 行{i+1}]: {line}")

        if extra_lines:
            result += "\n\n## 用户关键词相关行\n" + "\n".join(
                extra_lines[:10],
            )

        return result

    # ==================================================================
    # Stage 4: 知识库检索
    # ==================================================================

    def _search_knowledge(
        self, query: str, rule_suggestions: list, events: list,
    ) -> list:
        """搜索知识库：用户问题 + 规则命中 + 错误分类的组合查询。"""
        queries = [q for q in [query] if q.strip()]
        # 追加规则名称
        for s in rule_suggestions[:3]:
            queries.append(s.get("rule", ""))
        combined = " ".join(queries)
        if not combined.strip():
            combined = " ".join(
                e.get("classification", "")
                for e in events if e.get("is_error")
            )[:200]
        if not combined.strip():
            return []
        try:
            result = self.knowledge.search(combined, page_size=5)
            return result.get("items", [])
        except Exception:
            return []

    # ==================================================================
    # Stage 5: Prompt 构建
    # ==================================================================

    def _build_prompt(
        self,
        events: list,
        error_events: list,
        rule_summary: str,
        knowledge_summary: str,
        trimmed_log: str,
        user_query: str,
    ) -> str:
        """构建 LLM prompt — 使用裁剪后的关键日志，而非完整原始日志。"""
        parts = [self.DIAGNOSIS_PROMPT]

        # 用户问题（最高优先级）
        if user_query:
            parts.append(f"## 用户问题\n{user_query}\n")

        # 统计摘要
        parts.append(
            f"## 日志统计\n"
            f"解析事件总数: {len(events)}，"
            f"错误事件: {len(error_events)}，"
            f"正常事件: {len(events) - len(error_events)}"
        )

        # 规则引擎结果
        parts.append(f"## 规则引擎匹配结果\n{rule_summary}")

        # 知识库检索结果
        parts.append(f"## 知识库相关案例\n{knowledge_summary}")

        # 关键错误日志片段（已裁剪）
        parts.append(f"## 关键错误日志片段\n```\n{trimmed_log}\n```")

        # 严重错误列表
        if error_events:
            critical_errors = [
                e for e in error_events
                if e.get("severity") in ("critical", "high")
                or e.get("level") in ("CRITICAL", "ERROR", "FATAL")
            ]
            if critical_errors:
                error_summary = "\n".join(
                    f"- [{e.get('module', '?')}] {e.get('message', '')[:100]}"
                    for e in critical_errors[:10]
                )
                parts.append(f"## 严重错误摘要\n{error_summary}")

        parts.append("\n请输出 JSON 格式的完整诊断结果（不要用 markdown 代码块包裹）。")

        prompt = "\n\n".join(parts)
        logger.debug("[Pipeline] Prompt 长度: %d 字符", len(prompt))
        return prompt

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _format_rule_results(suggestions: list) -> str:
        if not suggestions:
            return "未匹配到已知规则。"
        return "\n".join(
            f"- [{s.get('rule', '')}] ({s.get('module', '')}): {s.get('message', '')}"
            for s in suggestions
        )

    @staticmethod
    def _format_knowledge_results(items: list) -> str:
        if not items:
            return "未找到相关知识库案例。"
        return "\n".join(
            f"{i + 1}. {item.get('title', '未知')} "
            f"(相关度: {item.get('relevance_score', 0):.0%}) — "
            f"{item.get('snippet', '')[:200]}"
            for i, item in enumerate(items[:3])
        )

    @staticmethod
    def _fallback_from_rules(events: list, suggestions: list) -> Dict[str, Any]:
        error_count = len([e for e in events if e.get("is_error")])
        if suggestions:
            top = suggestions[0]
            return {
                "summary": f"规则引擎匹配到 {len(suggestions)} 条已知问题。最可能: {top.get('message', '')}",
                "root_cause": f"规则引擎匹配结果: {top.get('rule', '')} ({top.get('module', '')})",
                "confidence": 0.65,
                "next_steps": [s.get("message", "") for s in suggestions[:5]],
                "rule_hits": len(suggestions),
                "knowledge_hits": 0,
                "event_count": len(events),
                "error_count": error_count,
            }
        return {
            "summary": f"检测到 {error_count} 个错误事件，建议上传更多日志进行深度分析。",
            "root_cause": "无法自动确定根因，规则引擎未匹配到已知模式。",
            "confidence": 0.3,
            "next_steps": [
                "检查设备硬件状态和驱动版本",
                "尝试通过管理后台添加自定义诊断规则",
                "上传更详细的日志进行二次分析",
            ],
            "rule_hits": 0,
            "knowledge_hits": 0,
            "event_count": len(events),
            "error_count": error_count,
        }

    @staticmethod
    def _normalize(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            try:
                return json.loads(payload.strip())
            except json.JSONDecodeError:
                m = _re_module.search(
                    r"```(?:json)?\s*(\{.*?\})\s*```", payload, _re_module.DOTALL,
                )
                if m:
                    try:
                        return json.loads(m.group(1))
                    except json.JSONDecodeError:
                        pass
                return {"summary": payload}
        return {"summary": str(payload)}

    @staticmethod
    def _normalize_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str):
            return [value]
        return []
