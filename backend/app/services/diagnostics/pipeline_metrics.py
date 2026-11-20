"""检索与预处理链的运维指标（P3 观测）。

设计原则：**只读数据库，不碰 broker / 不碰 Milvus 真实查询**，
这样运维接口本身不会成为故障源；向量侧状态单独走 vector_health()。

回答的问题：
  - 预处理链有没有积压、卡在哪个阶段、失败的都是谁；
  - 最近提问的检索质量信号（零命中率、耗时 P50/P95、结论分布）；
  - 向量库是不是语义向量、维度对不对、schema 是否兼容。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import AgentTask, ChatImageUpload, RetrievalTrace
from app.worker.task_state import STATUS_FAILED, STATUS_RUNNING, STATUS_SUCCEEDED

DEFAULT_WINDOW_HOURS = 24
RECENT_LIMIT = 2000


def _percentile(values: List[float], ratio: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
    return round(float(ordered[index]), 1)


def _as_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# 单价（元）：与 docs/16-Implementation/Chat-Image-Recognition-Design.md §6 一致
OCR_YUAN_PER_PAGE = 0.0015
VISION_YUAN_PER_INPUT_TOKEN = 2 / 1_000_000      # 高峰价，估算用
VISION_YUAN_PER_OUTPUT_TOKEN = 8 / 1_000_000


class PipelineMetrics:
    """预处理链 + 检索质量 + 向量库状态的只读快照。"""

    def __init__(self, db: Session, vector_service: Optional[Any] = None):
        self.db = db
        self._vector_service = vector_service

    # ------------------------------------------------------------------
    # 预处理链
    # ------------------------------------------------------------------

    def ingest_stats(self) -> Dict[str, Any]:
        tasks = self.db.query(AgentTask).all()
        by_status: Dict[str, int] = {}
        by_stage: Dict[str, Dict[str, int]] = {}
        failed: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        oldest_running: Optional[float] = None

        for task in tasks:
            by_status[task.status] = by_status.get(task.status, 0) + 1
            stage = str(task.state or "unknown")
            bucket = by_stage.setdefault(stage, {})
            bucket[task.status] = bucket.get(task.status, 0) + 1

            if task.status == STATUS_RUNNING:
                started = _as_utc(task.updated_at or task.created_at)
                if started is not None:
                    age = (now - started).total_seconds()
                    oldest_running = age if oldest_running is None else max(oldest_running, age)

            if task.status == STATUS_FAILED:
                failed.append({
                    "task_id": task.task_id,
                    "stage": stage,
                    "error": (task.error_message or "")[:200],
                })

        return {
            "total": len(tasks),
            "by_status": by_status,
            "by_stage": by_stage,
            "failed": failed[-20:],
            "running_oldest_seconds": round(oldest_running, 1) if oldest_running else None,
            "healthy": not failed,
        }

    # ------------------------------------------------------------------
    # 检索质量
    # ------------------------------------------------------------------

    def retrieval_stats(self, window_hours: int = DEFAULT_WINDOW_HOURS) -> Dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        rows = (
            self.db.query(RetrievalTrace)
            .filter(RetrievalTrace.created_at >= since)
            .order_by(RetrievalTrace.id.desc())
            .limit(RECENT_LIMIT)
            .all()
        )

        total_ms: List[float] = []
        zero_hit = 0
        conclusions: Dict[str, int] = {}

        for row in rows:
            timings = row.timings or {}
            if isinstance(timings, dict):
                value = timings.get("total_ms")
                if isinstance(value, (int, float)):
                    total_ms.append(float(value))

            kb = row.kb_candidates or {}
            candidates = kb.get("candidates") if isinstance(kb, dict) else None
            if not candidates:
                zero_hit += 1

            conclusion = row.conclusion or "unknown"
            conclusions[conclusion] = conclusions.get(conclusion, 0) + 1

        return {
            "window_hours": window_hours,
            "count": len(rows),
            "zero_hit_rate": round(zero_hit / len(rows), 4) if rows else None,
            "latency_ms": {
                "p50": _percentile(total_ms, 0.50),
                "p95": _percentile(total_ms, 0.95),
                "max": round(max(total_ms), 1) if total_ms else None,
            },
            "conclusions": conclusions,
        }

    # ------------------------------------------------------------------
    # 向量库
    # ------------------------------------------------------------------

    def _resolve_vector_service(self):
        if self._vector_service is not None:
            return self._vector_service
        from app.services.knowledge.vector_service import get_vector_service

        self._vector_service = get_vector_service()
        return self._vector_service

    def vector_health(self) -> Dict[str, Any]:
        try:
            from app.services.knowledge.embedding import get_embedder

            embedder = get_embedder()
            provider = embedder.provider_name
            dimension = embedder.dimension
            semantic = not provider.startswith("Hashing")
        except Exception as exc:  # noqa: BLE001
            return {"error": f"embedding: {exc}"}

        info: Dict[str, Any] = {
            "embedding_provider": provider,
            "embedding_dimension": dimension,
            "is_semantic": semantic,
        }

        try:
            service = self._resolve_vector_service()
            info["collection"] = service.collection_name
            info["milvus_available"] = service.available
            info["schema_error"] = getattr(service, "schema_error", None)
            collection = getattr(service, "_collection", None)
            if collection is not None:
                try:
                    info["entities"] = int(collection.num_entities)
                except Exception:  # noqa: BLE001 - 老版本/未 flush 时读不到
                    info["entities"] = None
        except Exception as exc:  # noqa: BLE001
            info["milvus_error"] = str(exc)

        return info

    # ------------------------------------------------------------------
    # 截图识别成本（I5）
    # ------------------------------------------------------------------

    def image_cost_stats(self, window_hours: int = DEFAULT_WINDOW_HOURS) -> Dict[str, Any]:
        """按 usage 汇总 OCR/视觉消耗与估算费用。

        估算用高峰单价（宁可高估），避免"看起来便宜"导致预算失控；
        真实账单以服务商为准。
        """
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        rows = (
            self.db.query(ChatImageUpload)
            .filter(ChatImageUpload.created_at >= since)
            .all()
        )

        by_status: Dict[str, int] = {}
        by_path: Dict[str, int] = {}
        ocr_pages = 0
        vision_in = 0
        vision_out = 0

        for row in rows:
            by_status[row.status] = by_status.get(row.status, 0) + 1
            if row.recognize_path:
                by_path[row.recognize_path] = by_path.get(row.recognize_path, 0) + 1
            usage = row.usage or {}
            if isinstance(usage, dict):
                try:
                    ocr_pages += int(usage.get("ocr_pages") or 0)
                except (TypeError, ValueError):
                    pass
                vision = usage.get("vision_usage") or {}
                if isinstance(vision, dict):
                    try:
                        vision_in += int(vision.get("prompt_tokens") or 0)
                        vision_out += int(vision.get("completion_tokens") or 0)
                    except (TypeError, ValueError):
                        pass

        cost = (
            ocr_pages * OCR_YUAN_PER_PAGE
            + vision_in * VISION_YUAN_PER_INPUT_TOKEN
            + vision_out * VISION_YUAN_PER_OUTPUT_TOKEN
        )
        return {
            "window_hours": window_hours,
            "images": len(rows),
            "by_status": by_status,
            "by_path": by_path,
            "ocr_pages": ocr_pages,
            "vision_input_tokens": vision_in,
            "vision_output_tokens": vision_out,
            "estimated_cost_yuan": round(cost, 4),
            "unit_prices": {
                "ocr_per_page": OCR_YUAN_PER_PAGE,
                "vision_input_per_token": VISION_YUAN_PER_INPUT_TOKEN,
                "vision_output_per_token": VISION_YUAN_PER_OUTPUT_TOKEN,
            },
        }

    def snapshot(self, window_hours: int = DEFAULT_WINDOW_HOURS) -> Dict[str, Any]:
        return {
            "ingest": self.ingest_stats(),
            "retrieval": self.retrieval_stats(window_hours),
            "vector": self.vector_health(),
            "image_cost": self.image_cost_stats(window_hours),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
