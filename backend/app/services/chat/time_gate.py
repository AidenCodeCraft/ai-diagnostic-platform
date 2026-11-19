"""时间窗闸门（P1 步骤 3）：用户给的时间是否落在日志覆盖范围内。

判定结果三态：
  - `None`：时间在范围内（或没有时间轴信息可判断）→ 继续正常流程；
  - `{"reply": ..., "options": [...], "awaiting": "time_choice"}`：不在范围内，
    回候选时段让用户选，并暂存状态以便下一轮续跑。

为什么必须给覆盖范围：只回「未找到」用户无法区分是记错时间、还是日志传错了。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.diagnostics.error_windows import (
    ErrorWindow,
    build_mismatch_reply,
    build_time_choice_options,
)
from app.services.diagnostics.log_timeline import TimelineManifest

TIME_FORMAT = "%Y-%m-%d %H:%M"
# 缺省放宽幅度：用户时间点前后各放宽这么多分钟来判定「是否够得上」
DEFAULT_TOLERANCE_MINUTES = 30


def _parse_slot_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in (TIME_FORMAT, "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def windows_from_payload(payload: Optional[List[Dict[str, Any]]]) -> List[ErrorWindow]:
    """从会话上下文恢复异常时段（JSON 里是字符串时间）。"""
    windows: List[ErrorWindow] = []
    for row in payload or []:
        try:
            start = datetime.strptime(str(row.get("start")), "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(str(row.get("end")), "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            continue
        windows.append(ErrorWindow(
            start=start,
            end=end,
            count=int(row.get("count") or 0),
            weight=int(row.get("weight") or 0),
            samples=[str(item) for item in (row.get("samples") or [])],
        ))
    return windows


def check_time_window(
    slots: Optional[Dict[str, Any]],
    log_analysis: Optional[Dict[str, Any]],
    *,
    tolerance_minutes: int = DEFAULT_TOLERANCE_MINUTES,
) -> Optional[Dict[str, Any]]:
    """时间不在日志覆盖范围内时，返回候选时段回复。"""
    slots = slots or {}
    asked = _parse_slot_time(slots.get("time"))
    if asked is None:
        return None

    timeline = (log_analysis or {}).get("timeline")
    if not timeline:
        return None
    manifest = TimelineManifest.from_dict(timeline)
    inside = manifest.contains(asked, tolerance_minutes=tolerance_minutes)
    if inside is None or inside:
        return None

    windows = windows_from_payload((log_analysis or {}).get("error_windows"))
    return {
        "awaiting": "time_choice",
        "asked": asked.strftime(TIME_FORMAT),
        "coverage": {
            "min": manifest.min_ts,
            "max": manifest.max_ts,
        },
        "reply": build_mismatch_reply(manifest, asked, windows),
        "options": build_time_choice_options(windows),
    }


def resolve_time_choice(
    choice: Optional[Dict[str, Any]],
) -> Optional[Dict[str, str]]:
    """把用户选中的时段转成时间窗（±5 分钟）。"""
    if not choice:
        return None
    try:
        start = datetime.strptime(str(choice.get("start")), "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(str(choice.get("end")), "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    from datetime import timedelta

    pad = timedelta(minutes=5)
    return {
        "start": (start - pad).strftime("%Y-%m-%d %H:%M:%S"),
        "end": (end + pad).strftime("%Y-%m-%d %H:%M:%S"),
    }
