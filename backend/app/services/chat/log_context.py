"""为「带日志提问」准备时间窗与日志片段（P1 步骤 5 的前置装配）。

只在时间窗确定后才读日志：默认窗口是用户给的时间点 ±30 分钟（或用户选中的
异常时段 ±5 分钟）。大文件按时间轴的字节偏移只读窗口那一段。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app.core.logging_config import get_logger
from app.services.diagnostics.log_timeline import TimelineManifest

logger = get_logger(__name__)

DEFAULT_PAD_MINUTES = 30
MAX_WINDOW_BYTES = 20 * 1024 * 1024   # 窗口上限，防止把整份日志读进内存


@dataclass
class LogContext:
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    data: Optional[bytes] = None
    window_label: str = ""
    reference: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "data": self.data,
            "window_label": self.window_label,
            "reference": self.reference,
        }


def _parse_time(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def resolve_window(
    slots: Optional[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
    *,
    pad_minutes: int = DEFAULT_PAD_MINUTES,
) -> tuple[Optional[datetime], Optional[datetime], str]:
    """确定本次要读的日志时间窗。

    优先级：用户选中的异常时段（±5 分钟）> 用户给的时间点（±pad_minutes）。
    """
    context = context or {}
    chosen = context.get("resolved_time_window")
    if isinstance(chosen, dict):
        start = _parse_time(chosen.get("start"))
        end = _parse_time(chosen.get("end"))
        if start and end:
            return start, end, f"{start.strftime('%m-%d %H:%M')} ~ {end.strftime('%H:%M')}"

    asked = _parse_time((slots or {}).get("time"))
    if asked is None:
        return None, None, ""
    start = asked - timedelta(minutes=pad_minutes)
    end = asked + timedelta(minutes=pad_minutes)
    return start, end, f"{asked.strftime('%m-%d %H:%M')} ±{pad_minutes}分钟"


def read_window(
    reference: str,
    manifest: Optional[TimelineManifest],
    start: Optional[datetime],
    end: Optional[datetime],
    *,
    max_bytes: int = MAX_WINDOW_BYTES,
) -> Optional[bytes]:
    """按时间窗读取日志片段（优先用 manifest 的字节偏移）。"""
    if not reference:
        return None
    try:
        from app.services.diagnostics.log_storage import LogStorage

        path = LogStorage().materialize(reference)
    except Exception as exc:  # noqa: BLE001 - 存储不可用时按「没有日志」处理
        logger.warning("[LogContext] materialize failed for %s: %s", reference, exc)
        return None

    path = Path(path)
    if not path.exists():
        logger.warning("[LogContext] log file missing: %s", path)
        return None

    if manifest and start and end:
        chunks = []
        total = 0
        for _key, byte_start, byte_end in manifest.window_offsets(start, end):
            if byte_end <= byte_start:
                continue
            length = min(byte_end - byte_start, max_bytes - total)
            if length <= 0:
                break
            with open(path, "rb") as handle:
                handle.seek(byte_start)
                chunks.append(handle.read(length))
            total += length
        if chunks:
            return b"".join(chunks)

    with open(path, "rb") as handle:
        return handle.read(max_bytes)


def build_log_context(
    slots: Optional[Dict[str, Any]],
    analysis: Optional[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
    *,
    loader: Optional[Callable[[str, Optional[TimelineManifest], Optional[datetime], Optional[datetime]], Optional[bytes]]] = None,
) -> Optional[LogContext]:
    """组装日志上下文；没有日志参考或没有时间窗时返回 None（等价于「按原逻辑回答」）。"""
    analysis = analysis or {}
    reference = str(
        analysis.get("reference")
        or analysis.get("file_path")
        or analysis.get("stored_path")
        or ""
    )
    start, end, label = resolve_window(slots, context)
    if not reference or start is None or end is None:
        return None

    manifest_payload = analysis.get("timeline")
    manifest = TimelineManifest.from_dict(manifest_payload) if manifest_payload else None

    if loader is not None:
        data = loader(reference, manifest, start, end)
    else:
        data = read_window(reference, manifest, start, end)

    return LogContext(
        start=start, end=end, data=data, window_label=label, reference=reference,
    )
