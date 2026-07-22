"""Diagnosis Pipeline — orchestrates Rule Engine → RAG → LLM for complete analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.services.knowledge.knowledge_service import KnowledgeService
from app.services.infrastructure.llm_service import LLMService
from app.services.diagnostics.parser_service import LogParserService
from app.services.system.rule_engine import RuleEngine

logger = get_logger(__name__)


class DiagnosisPipeline:
    """Full diagnostic pipeline: Parse → Rule Engine → RAG → LLM Synthesis.

    Implements the prescribed flow:
    1. Parse raw log files into structured events
    2. Run deterministic rule engine for known issues
    3. Search knowledge base for similar historical cases
    4. Send enriched context to LLM for final synthesis
    """

    DIAGNOSIS_PROMPT = (
        "你是一名资深的嵌入式系统与设备诊断工程师。"
        "请根据以下信息进行综合分析，给出准确的诊断结果。\n\n"
        "## 分析规则\n"
        "1. 优先参考【规则引擎结果】和【知识库案例】，它们是历史经验的积累。\n"
        "2. 结合【日志解析结果】进行综合判断。\n"
        "3. 输出必须使用中文，且为合法的 JSON 格式。\n"
        "4. 置信度要考虑规则引擎和知识库的匹配程度。\n\n"
        "## 输入信息\n\n"
    )

    def __init__(self, db: Session, model: Optional[str] = None):
        self.db = db
        self.model = model
        self.parser = LogParserService()
        self.rule_engine = RuleEngine()
        self.knowledge = KnowledgeService(db)

    def run(self, file_path: str, user_query: str = "") -> Dict[str, Any]:
        """Execute the full diagnostic pipeline.

        Returns a dict with: summary, root_cause, confidence, next_steps, rule_hits, knowledge_hits.
        """
        logger.info("Diagnosis pipeline starting: file=%s query=%s", Path(file_path).name, user_query[:50])

        # Step 1: Parse log file
        raw_events = self.parser.parse_structured(file_path)
        events = [e.to_dict() for e in raw_events]
        log_content = Path(file_path).read_text(encoding="utf-8", errors="ignore")[:8000]
        logger.debug("Parse complete: %d events, %d bytes", len(events), len(log_content))

        # Step 2: Rule Engine — deterministic analysis
        rule_suggestions = self.rule_engine.generate_suggestions(raw_events)  # type: ignore[arg-type]
        rule_summary = self._format_rule_results(rule_suggestions)
        logger.debug("Rule engine: %d suggestions", len(rule_suggestions))

        # Step 3: RAG — search knowledge base
        knowledge_results = self._search_knowledge(user_query, rule_suggestions, events)
        knowledge_summary = self._format_knowledge_results(knowledge_results)
        logger.debug("RAG: %d knowledge hits", len(knowledge_results))

        # Step 4: Build enriched prompt for LLM
        prompt = self._build_prompt(
            events=events,
            rule_summary=rule_summary,
            knowledge_summary=knowledge_summary,
            log_content=log_content,
            user_query=user_query,
        )

        # Step 5: LLM Synthesis
        try:
            llm_result = LLMService(model=self.model).generate_summary(
                log_content=prompt, events=events
            )
            logger.info("Diagnosis pipeline completed: confidence=%.2f", llm_result.get("confidence", 0))
        except Exception as exc:
            logger.warning("LLM synthesis failed — falling back to rule engine: %s", exc)
            return self._fallback_from_rules(events, rule_suggestions)

        payload = self._normalize(llm_result)
        summary = payload.get("summary", "分析完成") or "分析完成"
        root_cause = payload.get("root_cause", "请查看规则引擎匹配结果") or "请查看规则引擎匹配结果"
        confidence = float(payload.get("confidence", 0.5) or 0.5)
        next_steps = self._normalize_list(payload.get("next_steps", []))

        return {
            "summary": summary,
            "root_cause": root_cause,
            "confidence": confidence,
            "next_steps": next_steps,
            "rule_hits": len(rule_suggestions),
            "knowledge_hits": len(knowledge_results),
            "event_count": len(events),
            "error_count": len([e for e in events if e.get("is_error")]),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _search_knowledge(self, query: str, rule_suggestions: list, events: list) -> list:
        """Search knowledge base using user query + rule hits."""
        queries = [q for q in [query] if q.strip()]
        # Add rule names as search terms
        for s in rule_suggestions[:3]:
            queries.append(s.get("rule", ""))
        combined = " ".join(queries)
        if not combined.strip():
            # Fallback: use error categories
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

    def _build_prompt(
        self,
        events: list,
        rule_summary: str,
        knowledge_summary: str,
        log_content: str,
        user_query: str,
    ) -> str:
        parts = [self.DIAGNOSIS_PROMPT]
        if user_query:
            parts.append(f"## 用户问题\n{user_query}\n")
        parts.append(f"## 日志解析结果\n解析事件总数: {len(events)}，错误事件: {len([e for e in events if e.get('is_error')])}")
        parts.append(f"## 规则引擎匹配结果\n{rule_summary}")
        parts.append(f"## 知识库相关案例\n{knowledge_summary}")
        parts.append(f"## 原始日志摘要\n{log_content[:6000]}")
        parts.append("\n请输出 JSON 格式的完整诊断结果。")
        return "\n\n".join(parts)

    @staticmethod
    def _format_rule_results(suggestions: list) -> str:
        if not suggestions:
            return "未匹配到已知规则。"
        lines = []
        for s in suggestions:
            lines.append(f"- [{s.get('rule','')}] ({s.get('module','')}): {s.get('message','')}")
        return "\n".join(lines)

    @staticmethod
    def _format_knowledge_results(items: list) -> str:
        if not items:
            return "未找到相关知识库案例。"
        lines = []
        for i, item in enumerate(items[:3]):
            title = item.get("title", "未知")
            snippet = item.get("snippet", "")[:200]
            score = item.get("relevance_score", 0)
            lines.append(f"{i+1}. {title} (相关度: {score:.0%}) — {snippet}")
        return "\n".join(lines)

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
                # Try extracting JSON from markdown code blocks
                import re
                m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", payload, re.DOTALL)
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
