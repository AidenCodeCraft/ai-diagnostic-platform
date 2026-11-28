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
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from celery import chain, group
from celery.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.core.logging_config import get_logger
from app.worker.celery_app import EMBED_QUEUE, celery_app
from app.worker.ingest_service import (
    DEFAULT_CHUNK_BYTES,
    ChunkPlan,
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

def _session():
    from app.database import session as session_module

    return session_module.create_session()


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

        # 整条链一次性投递：parse 分片并发，之后 template → compress → index → finalize 串行。
        # 用 si()（immutable）——每步只吃自己的参数，不吃上一步返回值，
        # 避免 group 的返回值列表被当成下一个任务的入参。
        build_pipeline_chain(log_id, plans).apply_async()
        return {
            "stage": "prepare",
            "total_bytes": total_bytes,
            "chunks": len(plans),
            "progress": stage_progress("prepare", len(plans), len(plans)),
        }

    return _run_stage("prepare", log_id, worker)


@celery_app.task(name="ingest.parse", bind=True, max_retries=5, default_retry_delay=20)
def ingest_parse(self, log_id: int, chunk_no: int, start: int, length: int) -> Dict[str, Any]:
    """解析一个分片：规范化行 → JSONL 写产物存储（对象存储优先，本地兜底）。"""

    def worker(store: TaskStateStore) -> Dict[str, Any]:
        reference = _log_reference(log_id)
        if not reference:
            raise RuntimeError(f"log {log_id} 没有文件引用")

        from app.services.diagnostics.artifact_store import ArtifactStore
        from app.services.diagnostics.log_storage import LogStorage

        path = Path(LogStorage().materialize(reference))
        with open(path, "rb") as handle:
            handle.seek(start)
            data = handle.read(length)

        artifacts = ArtifactStore()
        buffer = io.BytesIO()
        parsed = 0
        unparsed = 0
        with gzip.GzipFile(fileobj=buffer, mode="wb") as out:
            for raw in data.split(b"\n"):
                line = raw.decode("utf-8", errors="replace").rstrip("\r")
                if not line:
                    continue
                record = normalize_line(line)
                if record is None:
                    unparsed += 1
                    continue
                out.write((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
                parsed += 1

        name = f"normalized_{chunk_no}.jsonl.gz"
        stored = artifacts.put(log_id, name, buffer.getvalue())

        return {
            "stage": "parse",
            "chunk_no": chunk_no,
            "parsed": parsed,
            "unparsed": unparsed,
            "artifact": stored,
        }

    return _run_stage("parse", log_id, worker, chunk_no=chunk_no)


@celery_app.task(name="ingest.template", bind=True, max_retries=3, default_retry_delay=15)
def ingest_template(self, log_id: int) -> Dict[str, Any]:
    """模板提取与聚合（Drain3 可用时用 Drain3，否则稳定哈希兜底）。"""

    def worker(store: TaskStateStore) -> Dict[str, Any]:
        from app.services.diagnostics.artifact_store import ArtifactStore

        from app.worker.ingest_service import (
            TEMPLATE_BATCH_SIZE,
            TEMPLATE_MINE_LIMIT,
            template_ids_batch,
            template_source,
        )

        artifacts = ArtifactStore()
        counter: Counter = Counter()
        total = 0
        mined = 0
        hashed_beyond_limit = 0
        for name in artifacts.normalized_names(log_id):
            data = artifacts.get(log_id, name) or b""
            try:
                text = gzip.decompress(data).decode("utf-8")
            except (OSError, UnicodeDecodeError):
                logger.warning("[ingest] 产物无法解压，跳过: %s", name)
                continue
            batch: List[str] = []

            def flush() -> None:
                nonlocal mined, hashed_beyond_limit
                if not batch:
                    return
                # 超过挖矿上限后只做哈希：模板是统计结果，不需要把每行都喂给 Drain3
                if mined >= TEMPLATE_MINE_LIMIT:
                    # 超限部分直接哈希：不走 Drain3，避免再碰文件锁（V4 实测会 PermissionError）
                    from app.worker.ingest_service import hash_template, mask_variables
                    for line in batch:
                        counter[hash_template(mask_variables(line))] += 1
                    hashed_beyond_limit += len(batch)
                else:
                    for tid in template_ids_batch(batch):
                        counter[tid] += 1
                    mined += len(batch)
                batch.clear()

            for line in text.splitlines():
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                total += 1
                batch.append(str(record.get("text", "")))
                if len(batch) >= TEMPLATE_BATCH_SIZE:
                    flush()
            flush()

        payload = {
            "stage": "template",
            "total_lines": total,
            "templates": len(counter),
            "template_source": template_source(),
            "mined_lines": mined,
            "hashed_beyond_limit": hashed_beyond_limit,
            "top": counter.most_common(20),
        }
        artifacts.put_text(log_id, "templates.json", json.dumps(payload, ensure_ascii=False))
        return payload

    return _run_stage("template", log_id, worker)


@celery_app.task(name="ingest.compress", bind=True, max_retries=2, default_retry_delay=15)
def ingest_compress(self, log_id: int) -> Dict[str, Any]:
    """模板化压缩（等价实现）：把规范化产物按模板分组再压缩。"""

    def worker(store: TaskStateStore) -> Dict[str, Any]:
        from app.services.diagnostics.artifact_store import ArtifactStore

        artifacts = ArtifactStore()
        raw_parts: List[str] = []
        compressed_bytes = 0
        for name in artifacts.normalized_names(log_id):
            data = artifacts.get(log_id, name) or b""
            compressed_bytes += len(data)
            try:
                raw_parts.append(gzip.decompress(data).decode("utf-8"))
            except (OSError, UnicodeDecodeError):
                logger.warning("[ingest] 产物无法解压，跳过: %s", name)

        raw_text = "".join(raw_parts)
        bundle = gzip.compress(raw_text.encode("utf-8"), compresslevel=9)
        artifacts.put(log_id, "compressed.bundle.jsonl.gz", bundle)

        raw_bytes = len(raw_text.encode("utf-8"))
        return {
            "stage": "compress",
            "raw_bytes": raw_bytes,
            "input_bytes": compressed_bytes,
            "after_bytes": len(bundle),
            # 压缩比相对「原始文本」计算：相对已压缩的分片算比值没有意义
            "ratio": round(raw_bytes / len(bundle), 2) if bundle else 0,
        }

    return _run_stage("compress", log_id, worker)


@celery_app.task(name="embed.log_index", bind=True, max_retries=3, default_retry_delay=30)
def log_index(self, log_id: int) -> Dict[str, Any]:
    """把日志证据块写入向量库（chunk_type=error/template，走 embed 队列）。"""

    def worker(store: TaskStateStore) -> Dict[str, Any]:
        from app.services.diagnostics.log_indexer import LogChunkIndexer

        return {"stage": "index", **LogChunkIndexer().index_log(log_id)}

    return _run_stage("index", log_id, worker)


def build_pipeline_chain(log_id: int, plans: List[ChunkPlan]):
    """构造完整处理链签名（便于离线断言，不需要 broker）。"""
    header = group(
        *[ingest_parse.si(log_id, plan.index, plan.start, plan.length) for plan in plans]
    )
    return chain(
        header,
        ingest_template.si(log_id),
        ingest_compress.si(log_id),
        log_index.si(log_id),
        ingest_finalize.si(log_id),
    )


@celery_app.task(name="ingest.finalize", bind=True)
def ingest_finalize(self, log_id: int) -> Dict[str, Any]:
    """汇总整条链状态，并把日志状态推进到 parsed。

    之前 finalize 只汇总任务状态，Log.status 永远停在 uploaded，
    前端/分析侧无法区分「预处理完成」与「仅上传」。
    """

    def worker(store: TaskStateStore) -> Dict[str, Any]:
        from app.models import Log

        summary = store.summary(log_id)
        log = store.db.query(Log).filter(Log.id == log_id).first()
        if log is not None and log.status in ("uploaded", "parsing"):
            log.status = "parsed"  # type: ignore[assignment]
            store.db.commit()
            logger.info("[ingest] log %s status -> parsed", log_id)
        return {"stage": "finalize", "summary": summary}

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
