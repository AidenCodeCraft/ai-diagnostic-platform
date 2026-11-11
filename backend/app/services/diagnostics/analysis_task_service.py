from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models import Analysis, Log

logger = get_logger(__name__)


class AnalysisTaskService:
    """Unified service for managing analysis task lifecycle.

    Merges AnalysisService + AnalysisResultService into a single,
    coherent service with proper status tracking.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Create / Start
    # ------------------------------------------------------------------

    def create_analysis(self, log_id: int, model: Optional[str] = None) -> Analysis:
        """Create a new analysis task for a given log."""
        log = self._get_log(log_id)
        logger.info("Creating analysis: log_id=%d model=%s", log_id, model or "mock")

        analysis = Analysis(
            log_id=log.id,
            status="pending",
            model=model or "mock",
        )
        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(analysis)
        return analysis

    def run_analysis(
        self, log_id: int, model: Optional[str] = None,
        user_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create and execute an analysis task end-to-end.

        Flow: pending → running → completed|failed
        
        Args:
            log_id: 日志ID
            model: LLM 模型名
            user_query: 用户的问题描述，用于引导分析方向
        """
        # Create or reuse existing analysis
        analysis = self.db.query(Analysis).filter(
            Analysis.log_id == log_id
        ).order_by(Analysis.created_at.desc()).first()

        if analysis is None:
            analysis = self.create_analysis(log_id, model)

        # Set status to running
        setattr(analysis, 'status', "running")
        self.db.commit()
        self.db.refresh(analysis)

        try:
            result = self._execute_analysis(analysis, user_query=user_query or "")
            setattr(analysis, 'status', "completed")
            self.db.commit()
            self.db.refresh(analysis)
            result["status"] = analysis.status
            return result
        except Exception as exc:
            setattr(analysis, 'status', "failed")
            setattr(analysis, 'error_message', str(exc))
            self.db.commit()
            raise

    def _execute_analysis(
        self, analysis: Analysis, user_query: str = "",
    ) -> Dict[str, Any]:
        """Core analysis: verify → pipeline(parse → rules → RAG → LLM) → persist."""
        log = self._get_log(int(analysis.log_id))  # type: ignore[arg-type]

        from pathlib import Path
        file_path = Path(str(log.file_path))
        if not file_path.exists():
            raise FileNotFoundError(f"Log file not found: {log.file_path}")

        if log.status in ("uploaded", "parsing", "parsed"):
            setattr(log, 'status', "analyzing")
            self.db.commit()

        # Run full diagnostic pipeline (Rule Engine + RAG + LLM)
        from app.services.diagnostics.diagnosis_pipeline import DiagnosisPipeline
        pipeline = DiagnosisPipeline(self.db, model=str(analysis.model or "mock"))
        result = pipeline.run(str(file_path), user_query=user_query or "")

        # Persist
        setattr(analysis, 'result', json.dumps(result))
        setattr(analysis, 'summary', result.get("summary", ""))
        setattr(analysis, 'root_cause', result.get("root_cause", ""))
        _confidence = result.get("confidence", 0.5)
        setattr(analysis, 'confidence', float(_confidence if _confidence is not None else 0.5))
        next_steps = result.get("next_steps", [])
        setattr(analysis, 'next_steps', json.dumps(self._normalize_next_steps(next_steps)))
        setattr(analysis, 'model', str(analysis.model or "diagnosis-pipeline"))

        self.db.commit()
        self.db.refresh(analysis)

        created_at_raw = analysis.created_at  # type: ignore[assignment]
        return {
            "id": analysis.id,
            "log_id": analysis.log_id,
            "status": analysis.status,
            "summary": analysis.summary,
            "root_cause": analysis.root_cause,
            "confidence": analysis.confidence,
            "next_steps": self._normalize_next_steps(analysis.next_steps),
            "model": analysis.model,
            "created_at": created_at_raw.isoformat() if created_at_raw is not None else None,
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_analysis(self, analysis_id: int) -> Analysis:
        analysis = self.db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if not analysis:
            raise ValueError("analysis not found")
        return analysis

    def get_analysis_by_log(self, log_id: int) -> Analysis:
        analysis = self.db.query(Analysis).filter(Analysis.log_id == log_id).first()
        if not analysis:
            raise ValueError("analysis not found")
        return analysis

    def list_analyses(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = self.db.query(Analysis)
        if status:
            query = query.filter(Analysis.status == status)

        total = query.count()
        items = (
            query.order_by(Analysis.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_result(self, analysis_id: int) -> Dict[str, Any]:
        """Return structured analysis result, including pre-formatted Markdown."""
        analysis = self.get_analysis(analysis_id)
        confidence_pct = ((analysis.confidence or 0) * 100)
        confidence_str = f"{confidence_pct:.0f}%"
        summary = str(analysis.summary or "")
        root_cause = str(analysis.root_cause or "")
        next_steps = self._normalize_next_steps(analysis.next_steps)

        # 解析原始结果 JSON（含证据 / 定位 / 无支撑标记）
        raw_result: Dict[str, Any] = {}
        if analysis.result:
            try:
                parsed = json.loads(str(analysis.result))
                if isinstance(parsed, dict):
                    raw_result = parsed
            except (json.JSONDecodeError, TypeError):
                raw_result = {}
        detections = raw_result.get("detections", []) or []
        evidence = raw_result.get("evidence", []) or []
        support_missing = bool(raw_result.get("support_missing", False))
        log_facts = raw_result.get("log_facts", []) or []

        # Pre-compute the Markdown representation on backend
        if summary or root_cause:
            markdown_lines: List[str] = [
                "## 诊断结果",
                "",
                "### 诊断摘要",
                summary or "分析完成",
                "",
                "### 根因分析",
                root_cause or "根因待确认",
                "",
                f"诊断置信度：**{confidence_str}**",
                "",
            ]
            if support_missing:
                markdown_lines.append("> 知识库中暂无支撑，本结果未输出推测性诊断结论。")
                markdown_lines.append("")
            if evidence:
                markdown_lines.append("### 知识库证据")
                for d in evidence:
                    matched = "、".join(
                        f"L{m.get('line_no')}" for m in (d.get("matched_lines") or [])[:10]
                    )
                    verdict_cn = {"hit": "命中", "partial": "部分命中", "miss": "未命中"}.get(
                        d.get("verdict"), ""
                    )
                    markdown_lines.append(
                        f"- 《{d.get('title', '')}》判定：{verdict_cn}；命中行：{matched or '无'}"
                    )
                markdown_lines.append("")
            if log_facts:
                markdown_lines.append("### 日志事实")
                markdown_lines.extend(str(f) for f in log_facts)
                markdown_lines.append("")
            markdown_lines.append("### 建议措施")
            for i, s in enumerate(next_steps):
                markdown_lines.append(f"{i + 1}. {s}")
            diagnosis_markdown = "\n".join(markdown_lines)
        else:
            diagnosis_markdown = ""

        created_at_raw = analysis.created_at  # type: ignore[assignment]
        updated_at_raw = analysis.updated_at  # type: ignore[assignment]
        return {
            "id": analysis.id,
            "log_id": analysis.log_id,
            "status": analysis.status,
            "summary": summary,
            "root_cause": root_cause,
            "confidence": analysis.confidence or 0.0,
            "next_steps": next_steps,
            "diagnosis_markdown": diagnosis_markdown,
            "detections": detections,
            "evidence": evidence,
            "support_missing": support_missing,
            "log_facts": log_facts,
            "model": analysis.model or "mock",
            "error_message": analysis.error_message,
            "created_at": created_at_raw.isoformat() if created_at_raw is not None else None,
            "updated_at": updated_at_raw.isoformat() if updated_at_raw is not None else None,
        }

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_analysis(self, analysis_id: int) -> None:
        analysis = self.get_analysis(analysis_id)
        self.db.delete(analysis)
        self.db.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_log(self, log_id: int) -> Log:
        log = self.db.query(Log).filter(Log.id == log_id).first()
        if not log:
            raise ValueError("log not found")
        return log

    @staticmethod
    def _normalize_payload(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            stripped = payload.strip()
            if not stripped:
                return {}
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return {"summary": stripped}
        return {"summary": str(payload)}

    @staticmethod
    def _normalize_next_steps(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except json.JSONDecodeError:
                pass
            return [stripped]
        return []
