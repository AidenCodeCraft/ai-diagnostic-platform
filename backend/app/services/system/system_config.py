"""系统参数（管理后台 → 系统配置 → 系统参数）读取。

配置持久化在 backend/data/raw/system_config.json 的 "system" 段，
与管理后台 API（app.api.admin）读写同一文件。键名统一为 snake_case，
读取时兼容旧版 camelCase 键。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

CONFIG_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "data", "raw", "system_config.json"
)

# 系统参数默认值（与管理后台「系统参数」表单一一对应）
DEFAULTS: Dict[str, Any] = {
    "max_upload_mb": 100,
    "timeout_seconds": 300,
    "log_retention_days": 90,
    # 多对话并行提问：开关 + 单用户最大并行提问对话数
    "parallel_chat_enabled": True,
    "max_parallel_chats": 3,
    # 最大同时在线人数（并发提问上限，0 = 不限制）
    "max_online_users": 200,
}

# 兼容旧版 camelCase 键名
KEY_ALIASES = {
    "maxUploadMb": "max_upload_mb",
    "timeoutSeconds": "timeout_seconds",
    "logRetentionDays": "log_retention_days",
    "parallelChatEnabled": "parallel_chat_enabled",
    "maxParallelChats": "max_parallel_chats",
    "maxOnlineUsers": "max_online_users",
}

_INT_KEYS = {
    "max_upload_mb", "timeout_seconds", "log_retention_days",
    "max_parallel_chats", "max_online_users",
}
_BOOL_KEYS = {"parallel_chat_enabled"}


def normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """把原始配置（含旧键名/脏数据）归一为完整的 snake_case 配置。"""
    result = dict(DEFAULTS)
    for key, value in (raw or {}).items():
        key = KEY_ALIASES.get(key, key)
        if key not in result:
            continue
        if key in _INT_KEYS:
            try:
                ivalue = int(value)
                if ivalue >= 0:
                    result[key] = ivalue
                continue
            except (TypeError, ValueError):
                continue
        if key in _BOOL_KEYS:
            result[key] = bool(value)
            continue
        result[key] = value
    return result


def get_system_config() -> Dict[str, Any]:
    """读取系统参数（默认值 + 文件配置）。每次调用读取小 JSON 文件，开销可忽略。"""
    raw: Dict[str, Any] = {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            raw = data.get("system") or {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        raw = {}
    return normalize(raw)
