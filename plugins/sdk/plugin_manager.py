"""Plugin Manager — centralized registry and lifecycle management."""

from __future__ import annotations

import importlib
import logging
from typing import Any, Dict, List, Optional, Type

from plugins.sdk.manifest import PluginManifest, PluginType
from plugins.sdk.plugin_base import PluginBase, PluginStatus

logger = logging.getLogger(__name__)


class PluginManager:
    """Central plugin registry that manages the full plugin lifecycle.

    Handles loading, initialization, enabling/disabling, and uninstalling
    of plugins by type (parser, rule, agent, llm, knowledge, report).
    """

    def __init__(self) -> None:
        self._plugins: Dict[str, PluginBase] = {}
        self._by_type: Dict[PluginType, Dict[str, PluginBase]] = {
            t: {} for t in PluginType
        }

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, plugin: PluginBase) -> None:
        """Register a plugin instance directly."""
        if plugin.name in self._plugins:
            raise ValueError(f"Plugin '{plugin.name}' already registered")

        plugin.on_install()
        plugin.on_load()
        plugin.on_initialize()
        plugin.on_enable()

        self._plugins[plugin.name] = plugin
        self._by_type[plugin.plugin_type][plugin.name] = plugin
        logger.info("Plugin registered: %s (type=%s)", plugin.name, plugin.plugin_type.value)

    def register_class(
        self,
        name: str,
        plugin_cls: Type[PluginBase],
        manifest_data: Optional[Dict[str, Any]] = None,
    ) -> PluginBase:
        """Register a plugin from its class with optional manifest overrides."""
        manifest = PluginManifest(
            name=name,
            version="0.1.0",
            plugin_type=plugin_cls.plugin_type,
        )
        if manifest_data:
            for k, v in manifest_data.items():
                if hasattr(manifest, k):
                    setattr(manifest, k, v)

        instance = plugin_cls(manifest)
        self.register(instance)
        return instance

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[PluginBase]:
        return self._plugins.get(name)

    def list_by_type(self, plugin_type: PluginType) -> List[PluginBase]:
        return list(self._by_type.get(plugin_type, {}).values())

    def list_running(self) -> List[PluginBase]:
        return [p for p in self._plugins.values() if p.is_running()]

    def list_all(self) -> List[PluginBase]:
        return list(self._plugins.values())

    # ------------------------------------------------------------------
    # Lifecycle control
    # ------------------------------------------------------------------

    def disable(self, name: str) -> None:
        plugin = self._require(name)
        plugin.on_disable()

    def enable(self, name: str) -> None:
        plugin = self._require(name)
        plugin.on_initialize()
        plugin.on_enable()

    def uninstall(self, name: str) -> None:
        plugin = self._require(name)
        plugin.on_disable()
        plugin.on_uninstall()
        del self._plugins[name]
        del self._by_type[plugin.plugin_type][name]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        by_type = {}
        for pt in PluginType:
            plugins = self._by_type[pt]
            running = sum(1 for p in plugins.values() if p.is_running())
            by_type[pt.value] = {"total": len(plugins), "running": running}

        total = len(self._plugins)
        running = sum(1 for p in self._plugins.values() if p.is_running())

        return {"total": total, "running": running, "by_type": by_type}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require(self, name: str) -> PluginBase:
        plugin = self._plugins.get(name)
        if not plugin:
            raise ValueError(f"Plugin not found: {name}")
        return plugin
