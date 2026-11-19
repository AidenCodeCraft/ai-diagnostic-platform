"""日志处理任务链（P2 步骤 1）。

链路：prepare → parse_chunk ×N → template → compress → finalize

每个任务都：
  1. 先 claim（幂等）：已 succeeded 直接跳过；失败重试次数超限交人工；
  2. 执行纯逻辑（`ingest_service`）或轻量 IO；
  3. finish 写回状态与摘要。

产物先落本地 `UPLOAD_DIR/_ingest/{log_id}/`，后续再迁到对象存储——
先把链路跑通并保证幂等，比一次性做全存储层更重要。
"""

from __future__ import annotations

import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from celery.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.core.logging_config import get_logger
from app.worker.celery_app import EMBED_QUEUE, celery_app
from app.worker.ingest_service import (
    DEFAULT_CHUNK_BYTES,
    normalize_line,
    plan_chunks,
    stage_progress,
    template_id,
)
from app.worker.task_state import (
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    TaskStateStore,
)

logger = get_logger(__name__)

ARTIFACT_DIRNAME = "_ingest"


def _session():
    from app.database import session as session_module

    return session_module.create_session()


def _artifact_dir(log_id: int) -> Path:
    base = Path(str(getattr(settings, "UPLOAD_DIR", "data/raw")))
    path = base / ARTIFACT_DIRNAME / str(log_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _log_reference(log_id: int) -> str:
    from app.models import Log

    db = _session()
    try:
        log = db.query(Log).filter(Log.id == log_id).first()
        return str(getattr(log, "file_path", "") or "")
    finally:
        db.close()


def _run_stage(stage: str, log_id: int, worker, *, chunk_no: int = 0) -> Dict[str, Any]:
    """统一的「claim → 执行 → finish」包装。"""
    db = _session()
    store = TaskStateStore(db)
    try:
        claim = store.claim(log_id=log_id, stage=stage, chunk_no=chunk_no)
        if not claim["claimed"]:
            logger.info("[ingest] skip %s log=%s chunk=%s reason=%s",
                        stage, log_id, chunk_no, claim["reason"])
            return {"skipped": True, "reason": claim["reason"]}

        task = claim["task"]
        try:
            result = worker(store)
        except (SoftTimeLimitExceeded, Exception) as exc:  # noqa: BLE001
            store.finish(task, status=STATUS_FAILED, error=str(exc)[:500])
            raise
        store.finish(task, status=STATUS_SUCCEEDED, summary=json.dumps(result, ensure_ascii=False)[:1000])
        return result
    finally:
        db.close()


@celery_app.task(name="ingest.prepare", bind=True, max_retries=3, default_retry_delay=10)
def ingest_prepare(self, log_id: int, chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> Dict[str, Any]:
    """规划分片并投递解析任务。"""

    def worker(store: TaskStateStore) -> Dict[str, Any]:
        reference = _log_reference(log_id)
        if not reference:
            raise RuntimeError(f"log {log_id} 没有文件引用")

        from app.services.diagnostics.log_storage import LogStorage

        path = LogStorage().materialize(reference)
        total_bytes = Path(path).stat().st_size
        plans = plan_chunks(total_bytes, chunk_bytes)

        for plan in plans:
            ingest_parse.apply_async(
                args=[log_id, plan.index, plan.start, plan.length],
                queue="ingest",
            )
        return {
            "stage": "prepare",
            "total_bytes": total_bytes,
            "chunks": len(plans),
            "progress": stage_progress("prepare", len(plans), len(plans)),
        }

    return _run_stage("prepare", log_id, worker)


@celery_app.task(name="ingest.parse", bind=True, max_retries=5, default_retry_delay=20)
def ingest_parse(self, log_id: int, chunk_no: int, start: int, length: int) -> Dict[str, Any]:
    """解析一个分片：规范化行 → JSONL 落本地产物目录。"""

    def worker(store: TaskStateStore) -> Dict[str, Any]:
        reference = _log_reference(log_id)
        if not reference:
            raise RuntimeError(f"log {log_id} 没有文件引用")

        from app.services.diagnostics.log_storage import LogStorage

        path = Path(LogStorage().materialize(reference))
        with open(path, "rb") as handle:
            handle.seek(start)
            data = handle.read(length)

        target = _artifact_dir(log_id) / f"normalized_{chunk_no}.jsonl"
        parsed = 0
        unparsed = 0
        with gzip.open(f"{target}.gz", "wt", encoding="utf-8") as out:
            for raw in data.split(b"\n"):
                line = raw.decode("utf-8", errors="replace").rstrip("\r")
                if not line:
                    continue
                record = normalize_line(line)
                if record is None:
                    unparsed += 1
                    continue
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                parsed += 1

        return {
            "stage": "parse",
            "chunk_no": chunk_no,
            "parsed": parsed,
            "unparsed": unparsed,
            "artifact": str(target.with_suffix(".jsonl.gz")),
        }

    return _run_stage("parse", log_id, worker, chunk_no=chunk_no)


@celery_app.task(name="ingest.template", bind=True, max_retries=3, default_retry_delay=15)
def ingest_template(self, log_id: int) -> Dict[str, Any]:
    """模板提取与聚合（Drain3 可用时用 Drain3，否则稳定哈希兜底）。"""

    def worker(store: TaskStateStore) -> Dict[str, Any]:
        directory = _artifact_dir(log_id)
        counter: Counter = Counter()
        total = 0
        for path in sorted(directory.glob("normalized_*.jsonl.gz")):
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    counter[template_id(record.get("text", ""))] += 1
                    total += 1

        payload = {
            "stage": "template",
            "total_lines": total,
            "templates": len(counter),
            "top": counter.most_common(20),
        }
        (directory / "templates.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8",
        )
        return payload

    return _run_stage("template", log_id, worker)


@celery_app.task(name="ingest.compress", bind=True, max_retries=2, default_retry_delay=15)
def ingest_compress(self, log_id: int) -> Dict[str, Any]:
    """模板化压缩（等价实现）：把规范化产物按模板分组再压缩。"""

    def worker(store: TaskStateStore) -> Dict[str, Any]:
        directory = _artifact_dir(log_id)
        before = sum(path.stat().st_size for path in directory.glob("normalized_*.jsonl.gz"))
        bundle = directory / "compressed.bundle.jsonl.gz"
        lines: List[str] = []
        for path in sorted(directory.glob("normalized_*.jsonl.gz")):
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                lines.extend(handle.readlines())
        with gzip.open(bundle, "wt", encoding="utf-8", compresslevel=9) as out:
            out.writelines(lines)
        after = bundle.stat().st_size
        return {
            "stage": "compress",
            "before_bytes": before,
            "after_bytes": after,
            "ratio": round(before / after, 2) if after else 0,
        }

    return _run_stage("compress", log_id, worker)


@celery_app.task(name="ingest.finalize", bind=True)
def ingest_finalize(self, log_id: int) -> Dict[str, Any]:
    """汇总整条链状态。"""

    def worker(store: TaskStateStore) -> Dict[str, Any]:
        return {"stage": "finalize", "summary": store.summary(log_id)}

    return _run_stage("finalize", log_id, worker)


def enqueue_pipeline(log_id: int) -> Dict[str, str]:
    """入口：上传完成后调用，启动整条链。

    `retry=False`：broker 不可用时立刻失败（由调用方降级为「仅上传成功」），
    绝不能让上传请求卡在队列连接重试上。
    """
    result = ingest_prepare.apply_async(args=[log_id], queue="ingest", retry=False)
    return {"task_id": str(getattr(result, "id", "")), "log_id": str(log_id), "queue": "ingest"}


__all__ = [
    "ingest_prepare", "ingest_parse", "ingest_template", "ingest_compress",
    "ingest_finalize", "enqueue_pipeline", "EMBED_QUEUE",
]
