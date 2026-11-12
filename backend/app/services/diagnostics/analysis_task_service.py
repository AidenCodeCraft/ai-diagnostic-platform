from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models import Analysis, Log

logger = get_logger(__name__)

# 轻量线程池：避免长分析阻塞 HTTP 请求；生产可替换为 Celery/RQ
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="analysis")


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

    def run_analysis_async(
        self, log_id: int, model: Optional[str] = None,
        user_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建分析任务并在后台线程执行，立即返回 pending 状态。

        前端通过 GET /analyses/{id} 轮询状态，完成后取 /result。
        """
        log = self._get_log(log_id)
        analysis = Analysis(
            log_id=log.id,
            status="pending",
            model=model or "mock",
        )
        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(analysis)

        analysis_id = int(analysis.id)
        _EXECUTOR.submit(self._execute_async, analysis_id, user_query or "")
        return {
            "id": analysis_id,
            "log_id": log_id,
            "status": "pending",
            "model": model or "mock",
        }

    def run_batch_async(
        self, log_ids: List[int], model: Optional[str] = None,
        user_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """批量创建异步分析任务（逐条提交，单条失败不影响其他）。"""
        items = []
        for log_id in log_ids:
            try:
                items.append(self.run_analysis_async(
                    log_id, model=model, user_query=user_query,
                ))
            except Exception as exc:  # noqa: BLE001 - 批量任务单条失败可接受
                items.append({
                    "log_id": log_id,
                    "status": "failed",
                    "error": str(exc)[:300],
                })
        return {"items": items, "total": len(items)}

    @staticmethod
    def _execute_async(analysis_id: int, user_query: str) -> None:
        """后台执行入口：使用独立 DB 会话，更新 running → completed|failed。"""
        from app.database import session as session_module

        db = session_module.create_session()
        try:
            service = AnalysisTaskService(db)
            analysis = service.get_analysis(analysis_id)
            setattr(analysis, "status", "running")
            db.commit()
            try:
                service._execute_analysis(analysis, user_query=user_query)
                setattr(analysis, "status", "completed")
                db.commit()
            except Exception as exc:  # noqa: BLE001 - 后台任务需记录失败
                logger.exception("[AnalysisAsync] analysis %d failed", analysis_id)
                setattr(analysis, "status", "failed")
                setattr(analysis, "error_message", str(exc)[:2000])
                db.commit()
        finally:
            db.close()

    def _execute_analysis(
        self, analysis: Analysis, user_query: str = "",
    ) -> Dict[str, Any]:
        """Core analysis: verify → pipeline(parse → rules → RAG → LLM) → persist."""
        log = self._get_log(int(analysis.log_id))  # type: ignore[arg-type]

        from app.services.diagnostics.log_storage import LogStorage
        file_path = LogStorage().materialize(str(log.file_path))
        if not file_path.exists():
            raise FileNotFoundError(f"Log file not found: {log.file_path}")

        if log.status in ("uploaded", "parsing", "parsed"):
            setattr(log, 'status', "analyzing")
            self.db.commit()

        # Run full diagnostic pipeline (Rule Engine + RAG + LLM)
        from app.services.diagnostics.diagnosis_pipeline import DiagnosisPipeline
        pipeline = DiagnosisPipeline(self.db, model=str(analysis.model or "mock"))
        result = pipeline.run(str(file_path), user_query=user_query or "")

        # 无证据时，若缺少关键槽位则改为「反问引导」而非直接无结论
        if result.get("support_missing"):
            try:
                from app.services.chat.clarification import ClarificationService
                questions = ClarificationService(self.db).analyze(user_query or "")
                if questions:
                    result["needs_clarification"] = True
                    result["questions"] = [q.to_dict() for q in questions]
                    result["summary"] = "信息不足，无法唯一匹配知识库案例；请补充关键信息后重新分析。"
                    result["root_cause"] = "需要补充设备/现场/版本等关键信息后才能给出结论。"
                    result["confidence"] = 0.0
            except Exception:
                logger.debug("[_execute_analysis] clarification skipped", exc_info=True)

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
            "needs_clarification": bool(result.get("needs_clarification", False)),
            "questions": result.get("questions", []) or [],
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
        needs_clarification = bool(raw_result.get("needs_clarification", False))
        questions = raw_result.get("questions", []) or []

        # Pre-compute the Markdown representation on backend
        if needs_clarification and questions:
            clarify_lines: List[str] = ["## 需要补充信息", summary or "信息不足，请补充关键信息。", ""]
            for q in questions:
                options = "、".join(q.get("options") or [])
                hint = f"（{q.get('hint')}）" if q.get("hint") else ""
                clarify_lines.append(f"- **{q.get('label', '')}**{hint}：{options or '请补充'}")
            clarify_lines.append("")
            clarify_lines.append("补充以上信息后，请重新上传日志或补充说明以便继续分析。")
            diagnosis_markdown = "\n".join(clarify_lines)
        elif summary or root_cause:
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
                    title = d.get("title", "")
                    parts = []
                    for m in (d.get("matched_lines") or [])[:10]:
                        sec = m.get("section")
                        parts.append(
                            f"《{title} · {sec} · L{m.get('line_no')}》" if sec
                            else f"《{title} · L{m.get('line_no')}》"
                        )
                    matched = "、".join(parts)
                    verdict_cn = {"hit": "命中", "partial": "部分命中", "miss": "未命中"}.get(
                        d.get("verdict"), ""
                    )
                    markdown_lines.append(f"- 判定：{verdict_cn}；证据：{matched or '无'}")
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
            "needs_clarification": needs_clarification,
            "questions": questions,
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
