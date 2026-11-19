"""日志时间轴扫描（P1 步骤 2）。

目的只有一个：**先回答"这份日志里到底有没有这个时间"**，并产出「小时 → 字节偏移」
映射，让后续按时间窗定位只读那几 MB，而不是把 100MB 全读一遍。

设计要点：
  - 单遍流式读取（二进制 + 逐行解码），内存占用与文件大小无关；
  - 时间戳解析与用户提问的解析共用同一套口径（北京时间，见 chat/slot_gate.py）；
  - 解析不出的行计入 `unparsed_lines`，不丢弃内容（可能是多行堆栈的续行）；
  - 只产出元数据，不产出全量解析结果——那是后续 Phase 的事。
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, IO, List, Optional, Tuple, Union

from app.services.chat.slot_gate import LOG_TIMESTAMP_PATTERN

# 模块名 + 可选编号：`[NL668_4G_GetRegSta.. 0719]`
# 必须以字母开头，否则会把行首的时间戳 `[2026-08-02 ...]` 当成模块
MODULE_PATTERN = re.compile(r"\[\s*(?P<name>[A-Za-z][A-Za-z0-9_.]*)(?:\s+(?P<id>\d{4}))?\s*\]")

# 时间戳只在行首附近出现；超出该范围不看，避免正文里的时间串误判
TIMESTAMP_SCAN_CHARS = 64

DEFAULT_ENCODINGS = ("utf-8", "gb18030")


@dataclass
class TimelineManifest:
    """时间轴扫描产物（可序列化后随任务传递）。"""

    total_lines: int = 0
    parsed_lines: int = 0
    unparsed_lines: int = 0
    min_ts: Optional[str] = None
    max_ts: Optional[str] = None
    # "YYYY-MM-DD HH" -> [byte_start, line_no]
    hour_offsets: Dict[str, List[int]] = field(default_factory=dict)
    module_stats: Dict[str, int] = field(default_factory=dict)
    encoding: str = "utf-8"
    size_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_lines": self.total_lines,
            "parsed_lines": self.parsed_lines,
            "unparsed_lines": self.unparsed_lines,
            "min_ts": self.min_ts,
            "max_ts": self.max_ts,
            "hour_offsets": self.hour_offsets,
            "module_stats": self.module_stats,
            "encoding": self.encoding,
            "size_bytes": self.size_bytes,
        }

    @property
    def coverage(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        def _parse(value: Optional[str]) -> Optional[datetime]:
            if not value:
                return None
            try:
                return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None

        return _parse(self.min_ts), _parse(self.max_ts)

    def contains(self, ts: Optional[datetime], *, tolerance_minutes: int = 0) -> Optional[bool]:
        """该时间点是否落在日志覆盖范围内；无法判断（无时间戳）时返回 None。"""
        if ts is None:
            return None
        start, end = self.coverage
        if start is None or end is None:
            return None
        pad = timedelta(minutes=tolerance_minutes)
        return (start - pad) <= ts <= (end + pad)

    def window_offsets(
        self, start: datetime, end: datetime,
    ) -> List[Tuple[str, int, int]]:
        """时间窗对应的字节区间：[(hour_key, byte_start, byte_end)]。

        `byte_end` 取下一个小时桶的起点；最后一个桶到文件末尾。
        """
        if not self.hour_offsets:
            return []

        keys = sorted(self.hour_offsets.keys())
        selected: List[Tuple[str, int, int]] = []
        for idx, key in enumerate(keys):
            try:
                hour_start = datetime.strptime(key, "%Y-%m-%d %H")
            except ValueError:
                continue
            hour_end = hour_start + timedelta(hours=1)
            # 只保留与 [start, end] 有交集的桶（否则会多读一个无关小时）
            if hour_end <= start or hour_start > end:
                continue
            byte_start = int(self.hour_offsets[key][0])
            byte_end = int(self.hour_offsets[keys[idx + 1]][0]) if idx + 1 < len(keys) else self.size_bytes
            selected.append((key, byte_start, byte_end))
        return selected


def _decode_line(raw: bytes, encoding: str) -> str:
    try:
        return raw.decode(encoding, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return raw.decode("utf-8", errors="replace")


def _detect_encoding(sample: bytes) -> str:
    for encoding in DEFAULT_ENCODINGS:
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def extract_timestamp(line: str) -> Optional[datetime]:
    """取行首附近的时间戳（必须是完整到秒的格式，避免正文误判）。"""
    match = LOG_TIMESTAMP_PATTERN.search(line[:TIMESTAMP_SCAN_CHARS])
    if not match:
        return None
    try:
        return datetime(
            int(match.group("y")), int(match.group("m")), int(match.group("d")),
            int(match.group("H")), int(match.group("M")), int(match.group("S")),
        )
    except ValueError:
        return None


def extract_module(line: str) -> Optional[str]:
    match = MODULE_PATTERN.search(line[:TIMESTAMP_SCAN_CHARS * 2])
    if not match:
        return None
    module_id = match.group("id")
    name = match.group("name")
    return f"{name}:{module_id}" if module_id else name


def scan_stream(stream: IO[bytes], *, encoding: Optional[str] = None) -> TimelineManifest:
    """扫描一个二进制流（可来自对象存储的流式响应）。"""
    manifest = TimelineManifest()
    offset = 0
    line_no = 0

    first_chunk = stream.read(4096)
    manifest.encoding = encoding or _detect_encoding(first_chunk or b"")
    buffer = first_chunk
    pending = b""

    def _handle(raw: bytes, start_offset: int, line_number: int) -> None:
        manifest.total_lines += 1
        line = _decode_line(raw, manifest.encoding)
        ts = extract_timestamp(line)
        if ts is None:
            manifest.unparsed_lines += 1
        else:
            manifest.parsed_lines += 1
            stamp = ts.strftime("%Y-%m-%d %H:%M:%S")
            if manifest.min_ts is None or stamp < manifest.min_ts:
                manifest.min_ts = stamp
            if manifest.max_ts is None or stamp > manifest.max_ts:
                manifest.max_ts = stamp
            hour_key = ts.strftime("%Y-%m-%d %H")
            manifest.hour_offsets.setdefault(hour_key, [start_offset, line_number])
        module = extract_module(line)
        if module:
            manifest.module_stats[module] = manifest.module_stats.get(module, 0) + 1

    while buffer:
        combined = pending + buffer
        position = 0
        while True:
            newline = combined.find(b"\n", position)
            if newline == -1:
                pending = combined[position:]
                break
            raw = combined[position:newline]
            if raw.endswith(b"\r"):
                raw = raw[:-1]
            _handle(raw, offset, line_no)
            # 偏移按「本行实际字节数」推进；用 newline 的绝对下标会重复计数
            offset += (newline + 1 - position)
            line_no += 1
            position = newline + 1
        buffer = stream.read(65536)

    if pending:
        _handle(pending, offset, line_no)
        offset += len(pending)

    manifest.size_bytes = offset
    return manifest


def scan_path(path: Union[str, Path], *, encoding: Optional[str] = None) -> TimelineManifest:
    """扫描本地文件（上传落盘 / materialize 之后的路径）。"""
    with open(path, "rb") as handle:
        return scan_stream(handle, encoding=encoding)


def scan_bytes(data: bytes, *, encoding: Optional[str] = None) -> TimelineManifest:
    return scan_stream(io.BytesIO(data), encoding=encoding)
