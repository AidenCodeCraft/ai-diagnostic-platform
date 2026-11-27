"""附日志提问的槽位闸门（P1 步骤 1）。

规则：附日志的提问必须带齐五项——城市、设备名、现象描述、时间点（北京时间）、附件。
缺项一次性追问，不连环问，也**不允许默认"现在"**充当时间点：检索范围会因此发散，
回答只能靠猜。

设计取舍：
  - 先用确定性规则抽取（正则 + 城市白名单 + 现象词表），LLM 只作为可选增强；
    规则能覆盖绝大多数真实提问，且可回归测试，不会今天抽得出、明天抽不出；
  - 时间解析统一返回北京时间 naive datetime，与全链路（日志时间戳）同一口径；
  - 抽取结果是「槽位字典」而不是一句话，便于清空重填与轨迹落库。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

# 常见城市/地区白名单（可通过 settings.SLOT_CITY_WHITELIST 追加）
DEFAULT_CITIES = (
    "北京", "上海", "广州", "深圳", "天津", "重庆", "成都", "杭州", "武汉", "西安",
    "南京", "苏州", "郑州", "长沙", "东莞", "佛山", "合肥", "福州", "厦门", "济南",
    "青岛", "昆明", "南宁", "贵阳", "乌鲁木齐", "兰州", "哈尔滨", "长春", "沈阳",
    "大连", "石家庄", "太原", "南昌", "海口", "三亚", "宁波", "无锡", "温州", "常州",
    "徐州", "烟台", "嘉兴", "泉州", "珠海", "中山", "惠州", "汕头", "台州", "保定",
)

# 现象词表：命中即认为「现象描述」齐全（可扩展）
PHENOMENON_KEYWORDS = (
    "黑屏", "白屏", "花屏", "闪屏", "蓝屏", "死机", "卡死", "卡顿", "重启", "掉线",
    "断网", "离线", "不上线", "不上报", "无信号", "没信号", "信号弱", "无法开机",
    "开不了机", "无法启动", "无法连接", "连不上", "不识别", "识别不到", "无声音",
    "没声音", "杂音", "花音", "发热", "过热", "烫", "掉电", "耗电", "不充电",
    "充不进电", "电压异常", "异响", "漏水", "渗水", "进水", "定位偏", "漂移",
    "不定位", "无定位", "时间不同步", "录像丢失", "存储满", "无法拍照", "黑块",
    "模糊", "不亮", "闪灯", "报警", "误报", "漏报", "自动关机", "反复重启",
)

# 时间：绝对格式
_ABS_TIME_PATTERNS = (
    re.compile(r"(?P<y>20\d{2})[-/年](?P<m>\d{1,2})[-/月](?P<d>\d{1,2})日?\s*(?P<H>\d{1,2})[:：点时](?P<M>\d{1,2})"),
    re.compile(r"(?P<m>\d{1,2})月(?P<d>\d{1,2})日?\s*(?P<period>上午|下午|晚上|凌晨|中午)?\s*(?P<H>\d{1,2})[:：点时](?P<M>\d{1,2})"),
)
# 时间：相对日期
_RELATIVE_DAY = re.compile(r"(?P<rel>今天|昨天|前天|今日|昨日|前日)")
# 时间：只有时段（上午/下午/晚上 + 点），支持 "09:15" 与 "下午3点20"
_PERIOD_HOUR = re.compile(r"(?P<period>上午|下午|晚上|凌晨|中午)?\s*(?P<H>\d{1,2})\s*[点时:：](?P<M>\d{1,2})?")
_PERIODS = ("上午", "下午", "晚上", "凌晨", "中午")

# 设备名：字母+数字（L10 / NL668 / L-10 / DSJ8）
_DEVICE_PATTERN = re.compile(r"\b(?P<model>[A-Za-z]{1,5}[-_]?\d{2,4}[A-Za-z]?)\b")
_DEVICE_HINT = re.compile(r"(?:型号|设备名|设备是|机型)\s*[:：]?\s*(?P<model>[A-Za-z0-9\-_]{2,20})")

# 时间戳在日志里的常见前缀（用于时间轴扫描的同一套口径）
LOG_TIMESTAMP_PATTERN = re.compile(
    r"(?P<y>20\d{2})[-/](?P<m>\d{2})[-/](?P<d>\d{2})[ T](?P<H>\d{2}):(?P<M>\d{2}):(?P<S>\d{2})"
)


@dataclass
class SlotExtraction:
    """槽位抽取结果。"""

    slots: Dict[str, Any] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing

    def to_dict(self) -> Dict[str, Any]:
        return {"slots": dict(self.slots), "missing": list(self.missing), "complete": self.complete}


SLOT_LABELS = {
    "city": "城市",
    "device": "设备名（型号）",
    "phenomenon": "现象描述",
    "time": "时间点（北京时间）",
    "attachment": "日志附件",
}


def _normalize_hour(hour: int, period: Optional[str]) -> int:
    """把「下午3点」这类表述换算成 24 小时制。"""
    if period in ("下午", "晚上") and hour < 12:
        return hour + 12
    if period == "中午" and hour < 11:
        return hour + 12
    if period == "凌晨" and hour == 12:
        return 0
    return hour


def parse_beijing_time(text: str, *, now: Optional[datetime] = None) -> Optional[datetime]:
    """从文本解析北京时间；解析不出返回 None（绝不默认"现在"）。"""
    if not (text or "").strip():
        return None
    now = now or datetime.now()
    text = text.strip()

    # 1) 完整绝对时间
    for pattern in _ABS_TIME_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        groups = match.groupdict()
        year = int(groups.get("y") or now.year)
        month = int(groups["m"])
        day = int(groups["d"])
        hour = _normalize_hour(int(groups["H"]), groups.get("period"))
        minute = int(groups.get("M") or 0)
        try:
            return datetime(year, month, day, hour, minute)
        except ValueError:
            continue

    # 2) 相对日期 + 时段（昨天下午3点 / 今天 14:20）
    rel = _RELATIVE_DAY.search(text)
    if rel:
        delta = {"今天": 0, "今日": 0, "昨天": 1, "昨日": 1, "前天": 2, "前日": 2}[rel.group("rel")]
        base: date = (now - timedelta(days=delta)).date()
        for period_match in _PERIOD_HOUR.finditer(text):
            groups = period_match.groupdict()
            hour = _normalize_hour(int(groups["H"]), groups.get("period"))
            minute = int(groups.get("M") or 0)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return datetime(base.year, base.month, base.day, hour, minute)
        return None

    # 3) 只有时段（"下午三点二十" 需要中文数字，这里只处理阿拉伯数字）
    for period_match in _PERIOD_HOUR.finditer(text):
        groups = period_match.groupdict()
        hour = _normalize_hour(int(groups["H"]), groups.get("period"))
        minute = int(groups.get("M") or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return datetime(now.year, now.month, now.day, hour, minute)

    return None


def extract_city(text: str, *, cities: Optional[tuple] = None) -> Optional[str]:
    text = text or ""
    for city in cities or DEFAULT_CITIES:
        if city in text:
            return city
    # 兜底：「XX市 / XX区 / XX县」写法，取 2~4 字前缀
    match = re.search(r"([\u4e00-\u9fa5]{2,4})(?:市|区|县)", text)
    return match.group(1) if match else None


def extract_device(text: str) -> Optional[str]:
    text = text or ""
    hinted = _DEVICE_HINT.search(text)
    if hinted:
        return hinted.group("model").upper()
    for match in _DEVICE_PATTERN.finditer(text):
        model = match.group("model").upper()
        # 排除纯年份/时间片段（如 2026）与常见无意义词
        if model.isdigit():
            continue
        return model
    return None


def extract_phenomenon(text: str) -> Optional[str]:
    text = text or ""
    hits = [word for word in PHENOMENON_KEYWORDS if word in text]
    if hits:
        # 取最短的命中词作为规范化标签，完整描述留给模型
        return sorted(hits, key=len)[0]
    return None


def extract_slots(
    text: str,
    *,
    has_attachment: bool,
    now: Optional[datetime] = None,
    cities: Optional[tuple] = None,
) -> SlotExtraction:
    """抽取五项槽位并给出缺失项（缺项顺序固定，便于前端展示）。"""
    parsed_time = parse_beijing_time(text, now=now)
    slots: Dict[str, Any] = {
        "city": extract_city(text, cities=cities),
        "device": extract_device(text),
        "phenomenon": extract_phenomenon(text),
        "time": parsed_time.strftime("%Y-%m-%d %H:%M") if parsed_time else None,
        "attachment": bool(has_attachment),
    }
    missing = [key for key in ("city", "device", "phenomenon", "time", "attachment") if not slots.get(key)]
    return SlotExtraction(slots=slots, missing=missing)


def build_slot_clarification(missing: List[str]) -> str:
    """一次性把缺失项问完（不连环追问）。"""
    if not missing:
        return ""
    labels = "、".join(SLOT_LABELS.get(key, key) for key in missing)
    lines = [f"要定位这个问题，还需要你补充：{labels}。"]
    if "time" in missing:
        lines.append("时间请给到分钟（例如「2026-08-02 14:22」或「昨天下午3点」）——我会按北京时间处理。")
    if "attachment" in missing:
        lines.append("请把对应时段的日志文件一并附上。")
    return "\n".join(lines)


def merge_slots(previous: Optional[Dict[str, Any]], new: Dict[str, Any]) -> Dict[str, Any]:
    """补答合并：新值优先，空值不覆盖已有值。"""
    merged = dict(previous or {})
    for key, value in (new or {}).items():
        if value:
            merged[key] = value
    return merged
