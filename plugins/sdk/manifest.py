"""Plugin manifest — YAML-based plugin descriptor parsing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PluginType(str, Enum):
    PARSER = "parser"
    RULE = "rule"
    AGENT = "agent"
    LLM = "llm"
    KNOWLEDGE = "knowledge"
    REPORT = "report"


@dataclass
class PluginManifest:
    """Parsed representation of a plugin.yaml descriptor."""

    name: str
    version: str
    plugin_type: PluginType
    author: str = "unknown"
    description: str = ""
    entry: str = ""
    dependencies: List[str] = field(default_factory=list)
    permissions: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        return cls(
            name=data.get("name", ""),
            version=data.get("version", "0.1.0"),
            plugin_type=PluginType(data.get("type", "parser")),
            author=data.get("author", "unknown"),
            description=data.get("description", ""),
            entry=data.get("entry", ""),
            dependencies=data.get("dependencies", []),
            permissions=data.get("permissions", {}),
            config=data.get("config", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "type": self.plugin_type.value,
            "author": self.author,
            "description": self.description,
            "entry": self.entry,
            "dependencies": self.dependencies,
            "permissions": self.permissions,
            "config": self.config,
        }
