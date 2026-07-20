"""Plugin Management API."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from plugins.sdk.plugin_manager import PluginManager

router = APIRouter(prefix="/plugins", tags=["plugins"])

# Singleton plugin manager
_plugin_manager = PluginManager()


@router.get("/stats")
def get_plugin_stats() -> Dict[str, Any]:
    """Get plugin system statistics."""
    return _plugin_manager.stats()


@router.get("")
def list_plugins() -> Dict[str, Any]:
    """List all registered plugins grouped by type."""
    plugins = _plugin_manager.list_all()
    by_type: Dict[str, list] = {}
    for p in plugins:
        t = p.plugin_type.value
        by_type.setdefault(t, []).append({
            "name": p.name,
            "version": p.version,
            "status": p.status.value,
            "description": p.manifest.description,
        })
    return {"plugins": by_type, "total": len(plugins)}
