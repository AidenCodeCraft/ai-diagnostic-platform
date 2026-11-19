"""日志证据块构建与入向量库（P2 剩余项 2）。

知识章节与日志证据块共用一个 Milvus 集合，靠 `chunk_type` 隔离：
  - `section`  → 知识库章节，只被知识问答召回
  - `error`    → 日志中的报错事件（按模板 + 时间桶聚合）
  - `template` → 高频模板摘要（"这类日志出现了多少次"）

为什么按「模板 + 时间桶」聚合而不是按行入库：
  100MB 日志动辄几十万行，逐行入库既浪费空间又让检索退化成"命中一堆重复行"。
  聚合后一条记录 = 一个现象（何时、哪个模块、什么模板、出现多少次），
  才是诊断时真正需要的东西。
"""

from __future__ import annotations

import gzip
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.core.config import settings
from app.core.logging_config import get_logger
from app.services.knowledge.vector_service import (
    CHUNK_TYPE_ERROR,
    CHUNK_TYPE_TEMPLATE,
    MAX_CHUNKS_PER_DOC,
    MAX_CONTENT_LENGTH,
    VectorService,
)
from app.worker.ingest_service import template_id

logger = get_logger(__name__)

ARTIFACT_DIRNAME = "_ingest"
DEFAULT_BUCKET_SECONDS = 60
MAX_SAMPLES = 3
MAX_CHUNKS_PER_LOG = 2000
MIN_TEMPLATE_REPEAT = 2

# 报错线索：命中即为 error 块（诊断价值最高，不做重复次数过滤）
ERROR_HINT = re.compile(
    r"(error|fail(?:ed|ure)?|exception|timeout|timed out|refused|denied|"
    r"crash|panic|abort|disconnect|reset by peer|no route|unreachable|"
    r"错误|失败|异常|超时|断开|拒绝)",
    re.IGNORECASE,
)


@dataclass
class LogChunk:
    chunk_type: str
    ts: str
    title: str
    section: str
    content: str
    index_text: str
    content_hash: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "chunk_type": self.chunk_type,
            "ts": self.ts,
            "title": self.title,
            "section": self.section,
            "content": self.content,
            "index_text": self.index_text,
            "content_hash": self.content_hash,
        }


def is_error_line(text: str) -> bool:
    return bool(ERROR_HINT.search(text or ""))


def _bucket(ts: str, bucket_seconds: int) -> str:
    """把时间戳落到时间桶（默认 1 分钟）。解析失败时用原值。"""
    try:
        value = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return ts or ""
    if bucket_seconds <= 1:
        return value.strftime("%Y-%m-%d %H:%M:%S")
    floored = value.replace(second=0, microsecond=0)
    if bucket_seconds >= 60:
        step = max(1, bucket_seconds // 60)
        floored = floored - timedelta(minutes=floored.minute % step)
    return floored.strftime("%Y-%m-%d %H:%M:%S")


def build_log_chunks(
    records: Iterable[Dict[str, Any]],
    *,
    bucket_seconds: int = DEFAULT_BUCKET_SECONDS,
    max_chunks: int = MAX_CHUNKS_PER_LOG,
) -> List[LogChunk]:
    """把规范化日志行聚合成证据块。

    Args:
        records: [{"ts","module","text",...}]，来自 ingest 的 normalized_*.jsonl.gz
        bucket_seconds: 时间桶粒度（同一模板在桶内合并）
        max_chunks: 单日志入向量库的块数上限（防止百万行日志把集合灌爆）

    Returns:
        error 块在前（按出现次数降序），template 块在后
    """
    groups: Dict[tuple, Dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "samples": [], "ts": "", "module": "", "error": False}
    )

    for record in records:
        text = (record.get("text") or "").strip()
        if not text:
            continue
        ts = record.get("ts") or ""
        module = (record.get("module") or "").strip()
        tid = template_id(text)
        key = (tid, _bucket(ts, bucket_seconds), module)
        group = groups[key]
        group["count"] += 1
        group["ts"] = group["ts"] or ts
        group["module"] = group["module"] or module
        group["error"] = group["error"] or is_error_line(text)
        if len(group["samples"]) < MAX_SAMPLES and text not in group["samples"]:
            group["samples"].append(text[:500])

    chunks: List[LogChunk] = []
    for (tid, bucket_ts, module), group in groups.items():
        count = int(group["count"])
        if not group["error"] and count < MIN_TEMPLATE_REPEAT:
            continue          # 一次性正常日志没有诊断价值，不入库
        chunk_type = CHUNK_TYPE_ERROR if group["error"] else CHUNK_TYPE_TEMPLATE
        title = f"{module or 'log'} {bucket_ts}".strip()
        section = f"{tid} ×{count}"
        body = "\n".join(group["samples"])
        content = f"[{bucket_ts}] {module} 出现 {count} 次\n{body}"[:MAX_CONTENT_LENGTH]
        chunks.append(
            LogChunk(
                chunk_type=chunk_type,
                ts=bucket_ts,
                title=title[:512],
                section=section[:512],
                content=content,
                index_text=f"{title}\n{body}",
                content_hash=f"{tid}:{bucket_ts}:{module}",
            )
        )

    chunks.sort(key=lambda c: (c.chunk_type != CHUNK_TYPE_ERROR, c.section))
    return chunks[:max_chunks]


def read_artifacts(log_id: int) -> List[Dict[str, Any]]:
    """读取 ingest 产出的规范化行（对象存储优先，本地兜底）。

    多机部署时 parse 与 index 很可能不在同一台机器，只能通过产物存储读。
    """
    from app.services.diagnostics.artifact_store import ArtifactStore

    artifacts = ArtifactStore()
    records: List[Dict[str, Any]] = []
    for name in artifacts.normalized_names(log_id):
        data = artifacts.get(log_id, name) or b""
        try:
            text = gzip.decompress(data).decode("utf-8")
        except (OSError, UnicodeDecodeError):
            logger.warning("[log-indexer] 产物无法解压，跳过: %s", name)
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
    return records


class LogChunkIndexer:
    """把一条日志的证据块写进向量库（先清旧块，保证幂等）。"""

    def __init__(self, vector_service: Optional[VectorService] = None):
        self.vector_service = vector_service or VectorService()

    def index_log(self, log_id: int, records: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        chunks = build_log_chunks(records if records is not None else read_artifacts(log_id))
        if not chunks:
            return {"indexed": 0, "error_chunks": 0, "template_chunks": 0}

        # 重新索引必须幂等：先删该日志旧块（source 表达式），否则重复上传会翻倍
        self.vector_service.delete_by_expr(f'source == "log:{log_id}"')
        indexed = self.vector_service.index_log_chunks(log_id, [chunk.as_dict() for chunk in chunks])

        return {
            "indexed": indexed,
            "error_chunks": sum(1 for c in chunks if c.chunk_type == CHUNK_TYPE_ERROR),
            "template_chunks": sum(1 for c in chunks if c.chunk_type == CHUNK_TYPE_TEMPLATE),
            "id_space": -(log_id * MAX_CHUNKS_PER_DOC),
        }
