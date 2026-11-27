"""日志异常时段聚合（P1 步骤 3）。

用途：用户给的时间点不在日志覆盖范围内时，不能只说「没找到」——那样用户无法判断
是自己记错时间、还是日志上传错了。这里给出 3 个「异常聚集时段」供选择：
时段 + 异常行数 + 典型消息，用户点一下即可继续。

说明：这里用的是**通用异常词**（fail/error/timeout/panic…）作为启发式，
只用于「给用户挑时段」，不参与最终定位结论——定位关键字仍然只来自知识库命中章节。
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import IO, Dict, Iterable, List, Optional, Tuple

from app.services.diagnostics.log_timeline import (
    TimelineManifest,
    extract_timestamp,
    scan_stream,
)

# 通用异常词（中英混排）：只做「值不值得看一眼」的初筛
ANOMALY_TOKENS = (
    "error", "fail", "failed", "failure", "timeout", "timed out", "exception",
    "panic", "assert", "crash", "fatal", "refused", "unreachable", "reset by peer",
    "no signal", "not registered", "offline", "retry", "retries exhausted",
    "异常", "失败", "超时", "错误", "断开", "掉线", "离线", "无信号", "未响应",
    "重启", "死机", "看门狗", "复位", "断连", "超限", "过温", "欠压", "过压",
)

# 高权重词：命中一条也比普通 error 更值得优先展示
SEVERE_TOKENS = ("panic", "fatal", "crash", "assert", "oom", "watchdog", "死机", "看门狗")

DEFAULT_GAP_SECONDS = 120
DEFAULT_WINDOW_LIMIT = 3
MAX_SAMPLES_PER_WINDOW = 3


@dataclass
class AnomalyEvent:
    ts: datetime
    line: str
    weight: int = 1


@dataclass
class ErrorWindow:
    start: datetime
    end: datetime
    count: int = 0
    weight: int = 0
    samples: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "start": self.start.strftime("%Y-%m-%d %H:%M:%S"),
            "end": self.end.strftime("%Y-%m-%d %H:%M:%S"),
            "count": self.count,
            "weight": self.weight,
            "samples": list(self.samples),
        }

    def label(self) -> str:
        return f"{self.start.strftime('%m-%d %H:%M')} ~ {self.end.strftime('%H:%M')}（{self.count} 条异常）"


def classify_line(line: str) -> int:
    """返回行权重：0 = 正常，1 = 一般异常，2 = 严重异常。"""
    lowered = (line or "").lower()
    if any(token in lowered for token in SEVERE_TOKENS):
        return 2
    if any(token in lowered for token in ANOMALY_TOKENS):
        return 1
    return 0


def collect_anomalies(stream: IO[bytes], *, encoding: str = "utf-8") -> List[AnomalyEvent]:
    """单遍扫描，只收异常行（不保存全量内容）。"""
    events: List[AnomalyEvent] = []
    for raw in stream:
        try:
            line = raw.decode(encoding, errors="replace").rstrip("\r\n")
        except (LookupError, UnicodeDecodeError):
            continue
        weight = classify_line(line)
        if weight <= 0:
            continue
        ts = extract_timestamp(line)
        if ts is None:
            continue
        events.append(AnomalyEvent(ts=ts, line=line.strip(), weight=weight))
    return events


def cluster_windows(
    events: Iterable[AnomalyEvent],
    *,
    gap_seconds: int = DEFAULT_GAP_SECONDS,
) -> List[ErrorWindow]:
    """把时间相近的异常行聚成一个时段（间隔超过 gap 就切段）。"""
    ordered = sorted(events, key=lambda event: event.ts)
    windows: List[ErrorWindow] = []
    current: Optional[ErrorWindow] = None

    for event in ordered:
        if current is None or (event.ts - current.end).total_seconds() > gap_seconds:
            current = ErrorWindow(start=event.ts, end=event.ts)
            windows.append(current)
        current.end = max(current.end, event.ts)
        current.count += 1
        current.weight += event.weight
        if len(current.samples) < MAX_SAMPLES_PER_WINDOW:
            current.samples.append(event.line[:160])
    return windows


def top_windows(
    events: Iterable[AnomalyEvent],
    *,
    limit: int = DEFAULT_WINDOW_LIMIT,
    gap_seconds: int = DEFAULT_GAP_SECONDS,
) -> List[ErrorWindow]:
    """按时段权重（严重度加权计数）排序，取前 limit 个。"""
    windows = cluster_windows(events, gap_seconds=gap_seconds)
    windows.sort(key=lambda window: (window.weight, window.count), reverse=True)
    return windows[:limit]


def build_time_choice_options(windows: List[ErrorWindow]) -> List[Dict[str, object]]:
    """生成候选时段选项（含「其他」）。"""
    options: List[Dict[str, object]] = []
    for index, window in enumerate(windows, start=1):
        payload = window.to_dict()
        payload.update({"index": index, "label": window.label()})
        options.append(payload)
    options.append({"index": len(windows) + 1, "label": "其他（我自己指定时间）", "manual": True})
    return options


def build_mismatch_reply(
    manifest: TimelineManifest,
    asked: datetime,
    windows: List[ErrorWindow],
) -> str:
    """时间不在日志范围内时的回复文本（必须说明覆盖范围，不能只说「没找到」）。"""
    start, end = manifest.coverage
    covered = (
        f"{start.strftime('%Y-%m-%d %H:%M')} ~ {end.strftime('%Y-%m-%d %H:%M')}"
        if start and end else "无法确定（日志中没有可解析的时间戳）"
    )
    lines = [
        f"日志覆盖的时间范围是 {covered}（北京时间），你问的 "
        f"{asked.strftime('%Y-%m-%d %H:%M')} 不在其中。",
    ]
    if not windows:
        lines.append("该日志里也没有识别到明显异常时段，请确认日志是否上传正确或补充时间点。")
        return "\n".join(lines)

    lines.append("日志中最近的异常时段：")
    for index, window in enumerate(windows, start=1):
        lines.append(f"{index}. {window.label()} 例：{window.samples[0][:80] if window.samples else '—'}")
    lines.append("请选择其中一个时段，或直接告诉我具体时间。")
    return "\n".join(lines)


def analyze_log_for_windows(
    data: bytes,
    *,
    limit: int = DEFAULT_WINDOW_LIMIT,
    gap_seconds: int = DEFAULT_GAP_SECONDS,
) -> Tuple[TimelineManifest, List[ErrorWindow]]:
    """一次拿到时间轴与异常时段（小文件/测试路径）。"""
    manifest = scan_stream(io.BytesIO(data))
    events = collect_anomalies(io.BytesIO(data), encoding=manifest.encoding)
    return manifest, top_windows(events, limit=limit, gap_seconds=gap_seconds)
