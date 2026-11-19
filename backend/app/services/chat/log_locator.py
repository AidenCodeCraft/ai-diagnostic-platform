"""按知识库关键字在日志时间窗内定位异常块（P1 步骤 4 后半）。

输入是「模式列表 + 时间窗」，输出是「命中的行块」：
  - 命中行扩展上下文（默认 ±20 行）→ 重叠区间合并 → 按「命中模式种类 / 命中次数 / 严重度」
    排序取前 30 块；
  - 同时统计每个模式命中多少行，未命中的模式要能报出来（"知识库提到但日志没有痕迹"
    本身就是有价值的结论）。

约束：只在时间窗内读（小文件整体读，大文件按 manifest 的字节偏移发 Range GET）。
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, IO, List, Optional, Sequence, Tuple

from app.services.chat.log_patterns import LogPattern
from app.services.diagnostics.error_windows import classify_line
from app.services.diagnostics.log_timeline import TimelineManifest, extract_timestamp

DEFAULT_CONTEXT_LINES = 20
DEFAULT_BLOCK_LIMIT = 30
MAX_SAMPLE_LINES = 3


@dataclass
class LogBlock:
    line_start: int          # 1-based，含
    line_end: int
    hits: int = 0
    patterns: List[str] = field(default_factory=list)
    samples: List[str] = field(default_factory=list)
    weight: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_start": self.line_start,
            "line_end": self.line_end,
            "hits": self.hits,
            "patterns": list(self.patterns),
            "samples": list(self.samples),
            "weight": self.weight,
        }

    def rank_key(self) -> Tuple[int, int, int]:
        return (len(self.patterns), self.hits, self.weight)


@dataclass
class LocateResult:
    blocks: List[LogBlock] = field(default_factory=list)
    pattern_hits: Dict[str, int] = field(default_factory=dict)
    matched_lines: int = 0
    total_lines: int = 0

    @property
    def has_hits(self) -> bool:
        return bool(self.blocks)

    def missing_patterns(self, patterns: Sequence[LogPattern]) -> List[str]:
        return sorted({
            pattern.pattern for pattern in patterns
            if not self.pattern_hits.get(pattern.pattern.lower())
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blocks": [block.to_dict() for block in self.blocks],
            "pattern_hits": dict(self.pattern_hits),
            "matched_lines": self.matched_lines,
            "total_lines": self.total_lines,
        }


def _match_line(line: str, lowered_patterns: Sequence[Tuple[str, str]]) -> List[str]:
    lowered = line.lower()
    return [pattern for key, pattern in lowered_patterns if key in lowered]


def locate_lines(
    lines: Sequence[str],
    patterns: Sequence[LogPattern],
    *,
    context_lines: int = DEFAULT_CONTEXT_LINES,
    limit: int = DEFAULT_BLOCK_LIMIT,
    first_line_no: int = 1,
) -> LocateResult:
    """在给定的行序列里定位；`first_line_no` 用于把块行号映射回原文件。"""
    result = LocateResult(total_lines=len(lines))
    if not lines or not patterns:
        return result

    lowered_patterns = [(pattern.pattern.lower(), pattern.pattern) for pattern in patterns]
    hit_positions: List[int] = []
    for index, line in enumerate(lines):
        matched = _match_line(line, lowered_patterns)
        if not matched:
            continue
        result.matched_lines += 1
        hit_positions.append(index)
        for pattern in matched:
            key = pattern.lower()
            result.pattern_hits[key] = result.pattern_hits.get(key, 0) + 1

    if not hit_positions:
        return result

    # 命中行 → 上下文区间，重叠即合并
    ranges: List[List[int]] = []
    for position in hit_positions:
        start = max(0, position - context_lines)
        end = min(len(lines) - 1, position + context_lines)
        if ranges and start <= ranges[-1][1] + 1:
            ranges[-1][1] = max(ranges[-1][1], end)
        else:
            ranges.append([start, end])

    blocks: List[LogBlock] = []
    for start, end in ranges:
        block = LogBlock(line_start=start + first_line_no, line_end=end + first_line_no)
        patterns_in_block: List[str] = []
        for position in range(start, end + 1):
            line = lines[position]
            matched = _match_line(line, lowered_patterns)
            if matched:
                block.hits += 1
                block.weight += classify_line(line)
                for pattern in matched:
                    if pattern not in patterns_in_block:
                        patterns_in_block.append(pattern)
                if len(block.samples) < MAX_SAMPLE_LINES:
                    block.samples.append(line.strip()[:200])
        block.patterns = patterns_in_block
        blocks.append(block)

    blocks.sort(key=lambda block: block.rank_key(), reverse=True)
    result.blocks = blocks[:limit]
    return result


def locate_stream(
    stream: IO[bytes],
    patterns: Sequence[LogPattern],
    *,
    encoding: str = "utf-8",
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    context_lines: int = DEFAULT_CONTEXT_LINES,
    limit: int = DEFAULT_BLOCK_LIMIT,
) -> LocateResult:
    """流式读取（可选时间窗过滤）后在窗口内定位。"""
    lines: List[str] = []
    first_line_no = 1
    line_no = 0

    for raw in stream:
        line_no += 1
        line = raw.decode(encoding, errors="replace").rstrip("\r\n")
        if start or end:
            ts = extract_timestamp(line)
            if ts is not None:
                if start and ts < start:
                    continue
                if end and ts > end:
                    continue
                if first_line_no == 1 and not lines:
                    first_line_no = line_no
        lines.append(line)

    return locate_lines(
        lines, patterns, context_lines=context_lines, limit=limit, first_line_no=first_line_no,
    )


def locate_bytes(
    data: bytes,
    patterns: Sequence[LogPattern],
    *,
    encoding: str = "utf-8",
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    context_lines: int = DEFAULT_CONTEXT_LINES,
    limit: int = DEFAULT_BLOCK_LIMIT,
) -> LocateResult:
    return locate_stream(
        io.BytesIO(data), patterns,
        encoding=encoding, start=start, end=end,
        context_lines=context_lines, limit=limit,
    )


def locate_with_manifest(
    read_range,
    manifest: TimelineManifest,
    patterns: Sequence[LogPattern],
    *,
    start: datetime,
    end: datetime,
    context_lines: int = DEFAULT_CONTEXT_LINES,
    limit: int = DEFAULT_BLOCK_LIMIT,
) -> LocateResult:
    """按时间窗的字节偏移分段读取（对象存储 Range GET 场景）。

    Args:
        read_range: (byte_start, byte_end) -> bytes，由调用方提供（MinIO / 本地文件）
    """
    chunks: List[bytes] = []
    for _key, byte_start, byte_end in manifest.window_offsets(start, end):
        if byte_end <= byte_start:
            continue
        chunks.append(read_range(byte_start, byte_end))
    if not chunks:
        return LocateResult()

    joined = b"".join(chunks)
    # 窗口内行号无法直接换算，这里只保证块内偏移正确（行号以窗口起点为基准）
    return locate_bytes(
        joined, patterns, encoding=manifest.encoding,
        start=start, end=end, context_lines=context_lines, limit=limit,
    )
