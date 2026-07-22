"""Plugin Management API — register, list, toggle plugins."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from plugins.sdk.manifest import PluginType
from plugins.sdk.plugin_manager import PluginManager

router = APIRouter(prefix="/plugins", tags=["plugins"])

_plugin_manager = PluginManager()

# 启动时自动注册内置插件
def _init_builtin_plugins():
    try:
        from plugins.builtin.usb_parser import USBLogParser
        from plugins.builtin.bluetooth_parser import BluetoothLogParser
        _plugin_manager.register_class("usb-parser", USBLogParser)
        _plugin_manager.register_class("bluetooth-parser", BluetoothLogParser)
    except Exception:
        pass

_init_builtin_plugins()


@router.get("/stats")
def get_plugin_stats() -> Dict[str, Any]:
    return _plugin_manager.stats()


@router.get("")
def list_plugins() -> Dict[str, Any]:
    plugins = _plugin_manager.list_all()
    by_type: Dict[str, list] = {}
    for p in plugins:
        t = p.plugin_type.value
        by_type.setdefault(t, []).append({
            "name": p.name, "version": p.version,
            "status": p.status.value, "description": p.manifest.description,
        })
    return {"plugins": by_type, "total": len(plugins)}


@router.get("/models")
def list_models() -> list[Dict[str, Any]]:
    """Return available LLM models from plugins + built-in registry."""
    from app.services import ProviderRegistry
    registry = ProviderRegistry()
    models = []
    for name in registry.available_providers:
        provider = registry.get_provider(name)
        models.append({
            "name": name,
            "model": getattr(provider, 'model', getattr(provider, 'default_model', name)),
            "healthy": provider.health_check(),
            "source": "builtin",
        })
    return models


@router.post("/toggle/{name}")
def toggle_plugin(name: str):
    plugin = _plugin_manager.get(name)
    if not plugin:
        raise HTTPException(status_code=404, detail="plugin not found")
    if plugin.is_running():
        _plugin_manager.disable(name)
        return {"name": name, "status": "disabled"}
    else:
        _plugin_manager.enable(name)
        return {"name": name, "status": "running"}
