"""异步日志处理的纯逻辑部分（P2 步骤 1）。

这里只放可单测、无 IO 的函数：切分计划、行规范化、变量打码、模板提取。
真正读存储/写对象/更新任务状态在 tasks.py 与 task_state.py。

为什么先做这一层：任务一旦接进队列，出错重跑的成本很高；把可测逻辑先固化，
Worker 侧只做编排，问题才好定位（是「逻辑算错」还是「IO/重试错了」）。
"""

from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logging_config import get_logger
from app.services.diagnostics.log_timeline import extract_module, extract_timestamp

logger = get_logger(__name__)

_DRAIN_LOCK = threading.Lock()

STAGE_ORDER = ("prepare", "parse", "template", "compress", "finalize")

DEFAULT_CHUNK_BYTES = 50 * 1024 * 1024      # 单任务处理上限 50MB
MAX_CHUNKS = 64                             # 防止异常大文件把队列打爆

# 变量打码：必须在模板提取之前，否则 IP/十六进制/数字会把模板库炸成碎片
_MASK_RULES = (
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<IP>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<GUID>"),
    (re.compile(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}:\d{2}"), "<TS>"),
    (re.compile(r"\b\d{5,}\b"), "<NUM>"),
    # 1~4 位短数字（音量、计数、序号）：不掩码的话「同样结构不同数值」会各成一模板
    # 以 0 开头的 4 位编号（0719/0311 这类模块号）保留，它们是稳定标识
    (re.compile(r"(?<![\w.<])(?:[1-9]\d{0,3})(?![\w>])"), "<N>"),
)


@dataclass
class ChunkPlan:
    index: int
    start: int
    length: int

    @property
    def end(self) -> int:
        return self.start + self.length if self.length > 0 else self.start


def plan_chunks(total_bytes: int, chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> List[ChunkPlan]:
    """把文件切成任务分片（按字节，边界由后续解析按行对齐）。"""
    if total_bytes <= 0:
        return [ChunkPlan(index=0, start=0, length=0)]
    chunk_bytes = max(1, int(chunk_bytes))
    plans: List[ChunkPlan] = []
    start = 0
    index = 0
    while start < total_bytes and index < MAX_CHUNKS:
        length = min(chunk_bytes, total_bytes - start)
        plans.append(ChunkPlan(index=index, start=start, length=length))
        start += length
        index += 1
    return plans


def mask_variables(text: str) -> str:
    """把易变的值替换成占位符（模板提取之前的必要步骤）。"""
    masked = text or ""
    for pattern, token in _MASK_RULES:
        masked = pattern.sub(token, masked)
    return masked


def normalize_line(line: str) -> Optional[Dict[str, Any]]:
    """解析一行日志；没有时间戳的返回 None（多行堆栈的续行）。"""
    ts = extract_timestamp(line or "")
    if ts is None:
        return None
    return {
        "ts": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "module": extract_module(line) or "",
        "text": line.rstrip("\r\n"),
        "masked": mask_variables(line),
    }


def template_id(line: str) -> str:
    """模板标识：Drain3 可用时用聚类 id（`d<cluster_id>`），否则退化为稳定哈希。

    Drain3 不可用不是错误——模板聚合是增强项；但降级必须留痕（`template_source`），
    否则以后没人知道这些 template_id 是怎么来的。
    """
    masked = mask_variables(line)
    if template_source() == "drain3":
        with _DRAIN_LOCK:
            cluster = _drain_template(masked)
        if cluster is not None:
            return f"d{cluster}"
    digest = hashlib.sha1(masked.strip().encode("utf-8")).hexdigest()[:16]
    return f"h:{digest}"


def _drain_state_path() -> Path:
    """模板库快照路径（跨文件、跨批次共用）。"""
    base = Path(str(getattr(settings, "UPLOAD_DIR", "data/raw"))) / "_ingest"
    base.mkdir(parents=True, exist_ok=True)
    return base / "drain3_state.bin"


def _get_drain_miner():
    global _DRAIN_MINER
    if _DRAIN_MINER is not None:
        return _DRAIN_MINER
    from drain3 import TemplateMiner
    from drain3.file_persistence import FilePersistence
    from drain3.template_miner_config import TemplateMinerConfig

    config = TemplateMinerConfig()
    config.drain_depth = 4
    config.drain_sim_th = 0.4
    config.drain_max_children = 100
    config.drain_max_clusters = 1024
    # 关键：持久化。不落盘的模板库每次进程重启都从零学，template_id 跨文件对不上，
    # 「同类错误按模板聚合」直接失效。
    handler = FilePersistence(str(_drain_state_path()))
    _DRAIN_MINER = TemplateMiner(persistence_handler=handler, config=config)
    return _DRAIN_MINER


def _drain_template(masked: str) -> Optional[int]:
    global _DRAIN_WARNED
    try:
        miner = _get_drain_miner()
    except Exception:  # noqa: BLE001 - 依赖/状态文件异常一律退化到哈希
        # 必须留一条 warning：静默降级会让「模板 id 全是哈希」这件事几个月没人发现
        if not _DRAIN_WARNED:
            _DRAIN_WARNED = True
            logger.warning("[template] Drain3 不可用，退化为哈希模板（只提示一次）", exc_info=True)
        return None
    result = miner.add_log_message(masked)
    if isinstance(result, dict):
        cluster_id = result.get("cluster_id")
        return int(cluster_id) if cluster_id is not None else None
    return None


_DRAIN_MINER = None
_DRAIN_WARNED = False


def reset_drain_miner() -> None:
    """测试用：丢弃进程内模板库实例（状态文件仍在磁盘上）。"""
    global _DRAIN_MINER
    _DRAIN_MINER = None


def template_source() -> str:
    """当前模板来源：drain3 或 fallback。"""
    try:
        import drain3  # noqa: F401

        return "drain3"
    except ImportError:
        return "fallback-hash"


def stage_progress(stage: str, done: int, total: int) -> Dict[str, Any]:
    """给前端/日志用的进度描述。"""
    total = max(1, int(total or 0))
    percent = min(100, int(round(done / total * 100)))
    return {"stage": stage, "done": done, "total": total, "percent": percent}
