"""Tests for the Plugin System (Commit 014)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import pytest

# Ensure project root is on sys.path so plugins package is importable
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from plugins.sdk.manifest import PluginManifest, PluginType
from plugins.sdk.plugin_base import PluginBase, PluginStatus
from plugins.sdk.plugin_manager import PluginManager
from plugins.builtin.usb_parser import USBLogParser
from plugins.builtin.bluetooth_parser import BluetoothLogParser


# ------------------------------------------------------------------
# PluginManifest
# ------------------------------------------------------------------


def test_manifest_from_dict():
    data = {
        "name": "usb-parser",
        "version": "1.0.0",
        "type": "parser",
        "author": "Test Team",
        "description": "USB log parser",
        "dependencies": ["pyusb"],
        "permissions": {"filesystem": "read"},
    }
    manifest = PluginManifest.from_dict(data)
    assert manifest.name == "usb-parser"
    assert manifest.version == "1.0.0"
    assert manifest.plugin_type == PluginType.PARSER
    assert manifest.author == "Test Team"
    assert manifest.dependencies == ["pyusb"]


def test_manifest_to_dict():
    manifest = PluginManifest(
        name="test",
        version="2.0",
        plugin_type=PluginType.AGENT,
        description="test agent",
    )
    d = manifest.to_dict()
    assert d["name"] == "test"
    assert d["type"] == "agent"


def test_manifest_defaults():
    manifest = PluginManifest.from_dict({"name": "minimal"})
    assert manifest.version == "0.1.0"
    assert manifest.plugin_type == PluginType.PARSER
    assert manifest.author == "unknown"


# ------------------------------------------------------------------
# PluginBase
# ------------------------------------------------------------------


def test_plugin_lifecycle():
    manifest = PluginManifest(name="test", version="1.0", plugin_type=PluginType.PARSER)
    plugin = PluginBase(manifest)
    assert plugin.status == PluginStatus.INSTALLED
    assert plugin.name == "test"

    plugin.on_load()
    assert plugin.status == PluginStatus.LOADED

    plugin.on_initialize()
    assert plugin.status == PluginStatus.INITIALIZED

    plugin.on_enable()
    assert plugin.status == PluginStatus.RUNNING
    assert plugin.is_running() is True

    plugin.on_disable()
    assert plugin.status == PluginStatus.DISABLED
    assert plugin.is_running() is False


# ------------------------------------------------------------------
# PluginManager
# ------------------------------------------------------------------


def test_manager_register_plugin():
    manager = PluginManager()
    manifest = PluginManifest(name="p1", version="1.0", plugin_type=PluginType.PARSER)
    plugin = PluginBase(manifest)
    manager.register(plugin)
    assert manager.get("p1") is plugin
    assert manager.get("p1").is_running() is True


def test_manager_register_duplicate():
    manager = PluginManager()
    m1 = PluginManifest(name="dup", version="1.0", plugin_type=PluginType.PARSER)
    manager.register(PluginBase(m1))
    with pytest.raises(ValueError, match="already registered"):
        manager.register(PluginBase(m1))


def test_manager_list_by_type():
    manager = PluginManager()
    m1 = PluginManifest(name="parser_x", version="1.0", plugin_type=PluginType.PARSER)
    m2 = PluginManifest(name="rule_x", version="1.0", plugin_type=PluginType.RULE)
    manager.register(PluginBase(m1))
    manager.register(PluginBase(m2))

    parsers = manager.list_by_type(PluginType.PARSER)
    assert len(parsers) == 1
    assert parsers[0].name == "parser_x"

    rules = manager.list_by_type(PluginType.RULE)
    assert len(rules) == 1


def test_manager_disable_enable():
    manager = PluginManager()
    m = PluginManifest(name="toggle", version="1.0", plugin_type=PluginType.PARSER)
    manager.register(PluginBase(m))

    manager.disable("toggle")
    assert not manager.get("toggle").is_running()

    manager.enable("toggle")
    assert manager.get("toggle").is_running()


def test_manager_uninstall():
    manager = PluginManager()
    m = PluginManifest(name="remove", version="1.0", plugin_type=PluginType.PARSER)
    manager.register(PluginBase(m))
    assert manager.get("remove") is not None

    manager.uninstall("remove")
    assert manager.get("remove") is None


def test_manager_nonexistent():
    manager = PluginManager()
    with pytest.raises(ValueError):
        manager.disable("nonexistent")
    with pytest.raises(ValueError):
        manager.uninstall("nonexistent")


def test_manager_stats():
    manager = PluginManager()
    m1 = PluginManifest(name="stats_p1", version="1.0", plugin_type=PluginType.PARSER)
    m2 = PluginManifest(name="stats_p2", version="1.0", plugin_type=PluginType.RULE)
    manager.register(PluginBase(m1))
    manager.register(PluginBase(m2))
    manager.disable("stats_p2")

    stats = manager.stats()
    assert stats["total"] == 2
    assert stats["running"] == 1
    assert stats["by_type"]["parser"]["total"] == 1
    assert stats["by_type"]["parser"]["running"] == 1
    assert stats["by_type"]["rule"]["running"] == 0


def test_manager_register_class():
    manager = PluginManager()
    instance = manager.register_class("usb1", USBLogParser)
    assert instance.name == "usb1"
    assert instance.plugin_type == PluginType.PARSER
    assert manager.get("usb1") is instance


def test_manager_list_all():
    manager = PluginManager()
    for i in range(3):
        m = PluginManifest(name=f"p{i}", version="1.0", plugin_type=PluginType.PARSER)
        manager.register(PluginBase(m))
    assert len(manager.list_all()) == 3
    assert len(manager.list_running()) == 3


# ------------------------------------------------------------------
# Built-in Plugins
# ------------------------------------------------------------------


def test_usb_parser_detects_timeout():
    parser = USBLogParser(PluginManifest(name="usb", version="1.0", plugin_type=PluginType.PARSER))
    parser.on_initialize()

    event = parser.parse("kernel: [ 123.456789] usb 1-1: device not responding")
    assert event is not None
    assert event["module"] == "usb"
    assert event["classification"] == "timeout"
    assert event["is_error"] is True


def test_usb_parser_no_match():
    parser = USBLogParser(PluginManifest(name="usb", version="1.0", plugin_type=PluginType.PARSER))
    parser.on_initialize()

    event = parser.parse("INFO system: startup ok")
    assert event is None


def test_usb_parser_multi_line():
    parser = USBLogParser(PluginManifest(name="usb", version="1.0", plugin_type=PluginType.PARSER))
    parser.on_initialize()

    text = (
        "usb 1-1: device not responding\n"
        "usb 2-1: over-current condition\n"
        "INFO system: ok\n"
    )
    events = parser.parse_text(text)
    assert len(events) == 2
    assert events[0]["classification"] == "timeout"
    assert events[1]["classification"] == "over_current"


def test_bluetooth_parser_hci_timeout():
    parser = BluetoothLogParser(PluginManifest(name="bt", version="1.0", plugin_type=PluginType.PARSER))
    parser.on_initialize()

    event = parser.parse("Bluetooth: hci0 command 0x0401 timeout")
    assert event is not None
    assert event["module"] == "bluetooth"
    assert event["classification"] == "hci_timeout"


def test_bluetooth_parser_no_match():
    parser = BluetoothLogParser(PluginManifest(name="bt", version="1.0", plugin_type=PluginType.PARSER))
    parser.on_initialize()

    event = parser.parse("INFO wifi: connected to AP")
    assert event is None


def test_bluetooth_parser_multi_line():
    parser = BluetoothLogParser(PluginManifest(name="bt", version="1.0", plugin_type=PluginType.PARSER))
    parser.on_initialize()

    text = (
        "Bluetooth: hci0 command 0x0401 timeout\n"
        "Bluetooth: Connection lost\n"
        "INFO system: ok\n"
    )
    events = parser.parse_text(text)
    assert len(events) == 2
    assert events[0]["classification"] == "hci_timeout"
    assert events[1]["classification"] == "connection_error"


# ------------------------------------------------------------------
# PluginManager integration with ParserRegistry
# ------------------------------------------------------------------


def test_plugin_manager_integrates_with_parser_registry():
    from app.services.parser.registry import ParserRegistry

    registry = ParserRegistry()
    initial_count = len(registry.registered_sources)
    assert initial_count >= 2  # kernel + linux

    # Register a plugin-based parser (via the existing register method)
    # The registry already supports external registration
    registry.register(GenericParserStub())
    assert len(registry.registered_sources) == initial_count + 1


class GenericParserStub:
    source_type = "plugin_stub"

    def can_parse(self, line: str) -> bool:
        return False
