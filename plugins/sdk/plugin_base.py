"""Plugin SDK — abstract base class and lifecycle."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional

from plugins.sdk.manifest import PluginManifest, PluginType


class PluginStatus(str, Enum):
    INSTALLED = "installed"
    LOADED = "loaded"
    INITIALIZED = "initialized"
    RUNNING = "running"
    DISABLED = "disabled"
    ERROR = "error"


class PluginBase(ABC):
    """Abstract base for all AI Diagnostic Platform plugins.

    Lifecycle: install → load → initialize → running → disable → uninstall
    """

    plugin_type: PluginType = PluginType.PARSER

    def __init__(self, manifest: PluginManifest) -> None:
        self.manifest = manifest
        self.status = PluginStatus.INSTALLED
        self._error: Optional[str] = None
        # Use manifest type if available, otherwise class default
        if manifest.plugin_type:
            self.plugin_type = manifest.plugin_type

    # ------------------------------------------------------------------
    # Lifecycle hooks (override in subclass)
    # ------------------------------------------------------------------

    def on_install(self) -> None:
        """Called when the plugin is first installed."""
        self.status = PluginStatus.INSTALLED

    def on_load(self) -> None:
        """Called when the plugin is loaded into memory."""
        self.status = PluginStatus.LOADED

    def on_initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Called to initialize the plugin with optional config."""
        self.status = PluginStatus.INITIALIZED

    def on_enable(self) -> None:
        """Called when the plugin is enabled / set to running."""
        self.status = PluginStatus.RUNNING

    def on_disable(self) -> None:
        """Called when the plugin is disabled."""
        self.status = PluginStatus.DISABLED

    def on_uninstall(self) -> None:
        """Called before the plugin is removed."""

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def error(self) -> Optional[str]:
        return self._error

    def is_running(self) -> bool:
        return self.status == PluginStatus.RUNNING
