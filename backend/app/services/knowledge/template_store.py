"""知识模板自定义存储 — 允许用户修改格式说明/结构项/骨架/示例。

存储为 JSON 文件（默认 backend/data/knowledge/template_overrides.json），
作为内置模板（templates.py）的覆盖层；`templates.get_template()` 会自动合并。
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.logging_config import get_logger

logger = get_logger(__name__)

VALID_LEVELS = {"required", "recommended", "optional"}
_lock = threading.Lock()
_cache: Dict[str, Any] = {"mtime": None, "data": {}}


def _template_file() -> Path:
    try:
        from app.core.config import settings
        raw = getattr(settings, "KNOWLEDGE_TEMPLATE_FILE", "data/knowledge/template_overrides.json")
    except Exception:  # noqa: BLE001
        raw = "data/knowledge/template_overrides.json"
    path = Path(raw)
    if not path.is_absolute():
        # backend/app/services/knowledge/template_store.py → parents[3] = backend
        path = Path(__file__).resolve().parents[3] / path
    return path


def load_overrides() -> Dict[str, Dict[str, Any]]:
    """读取覆盖配置（带 mtime 缓存）。"""
    path = _template_file()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    with _lock:
        if _cache["mtime"] == mtime:
            return dict(_cache["data"])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[TemplateStore] read overrides failed: %s", exc)
        return {}
    if not isinstance(data, dict):
        return {}
    with _lock:
        _cache["mtime"] = mtime
        _cache["data"] = data
    return dict(data)


def get_override(doc_type: str) -> Optional[Dict[str, Any]]:
    return load_overrides().get((doc_type or "").strip().lower())


def _save(data: Dict[str, Any]) -> None:
    path = _template_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    with _lock:
        _cache["mtime"] = None
        _cache["data"] = data


def _normalize_sections(items: Any) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return sections
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        key = str(item.get("key") or "").strip()
        if not title:
            continue
        if not key:
            key = _slug(title)
        level = str(item.get("level") or "optional").strip().lower()
        if level not in VALID_LEVELS:
            level = "optional"
        aliases = [
            str(alias).strip() for alias in (item.get("aliases") or [])
            if str(alias).strip()
        ]
        sections.append({
            "key": key,
            "title": title,
            "level": level,
            "aliases": aliases,
        })
    return sections


def _slug(title: str) -> str:
    import re
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "_", title).strip("_").lower()
    return value or "section"


def upsert_override(doc_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """新增/更新某文档类型的格式覆盖。"""
    from app.services.knowledge.templates import TEMPLATES

    key = (doc_type or "").strip().lower()
    if key not in TEMPLATES:
        raise ValueError(f"未知文档类型: {doc_type}")

    overrides = load_overrides()
    entry = dict(overrides.get(key) or {})
    for field in ("name", "guide", "skeleton", "example"):
        if field in payload and payload[field] is not None:
            entry[field] = str(payload[field])
    if "free_form" in payload and payload["free_form"] is not None:
        entry["free_form"] = bool(payload["free_form"])
    if "sections" in payload:
        entry["sections"] = _normalize_sections(payload["sections"])
    overrides[key] = entry
    _save(overrides)
    return entry


def reset_override(doc_type: str) -> bool:
    """删除某类型的覆盖，恢复内置模板。"""
    key = (doc_type or "").strip().lower()
    overrides = load_overrides()
    if key not in overrides:
        return False
    overrides.pop(key, None)
    _save(overrides)
    return True
