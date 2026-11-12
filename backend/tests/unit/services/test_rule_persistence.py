"""规则引擎 JSON 持久化。"""

import json

from app.services.system.rule_engine import RuleEngine


class TestRulePersistence:
    def test_explicit_rules_do_not_touch_file(self, tmp_path):
        path = tmp_path / "rules.json"
        engine = RuleEngine(rules=[{"name": "r1", "match": "timeout", "suggestion": "s"}])
        engine.add_rule("r2", "panic", "check")
        assert not path.exists()

    def test_add_and_reload(self, tmp_path):
        path = tmp_path / "rules.json"
        engine = RuleEngine(storage_path=path)
        engine.add_rule("custom-timeout", "timeout", "自定义建议")

        reloaded = RuleEngine(storage_path=path)
        names = [rule["name"] for rule in reloaded.list_rules()]
        assert "custom-timeout" in names
        assert "usb-timeout" in names  # 内置规则仍在

    def test_remove_persists(self, tmp_path):
        path = tmp_path / "rules.json"
        engine = RuleEngine(storage_path=path)
        assert engine.remove_rule("failure") is True
        assert engine.remove_rule("missing-rule") is False

        reloaded = RuleEngine(storage_path=path)
        names = [rule["name"] for rule in reloaded.list_rules()]
        assert "failure" not in names

    def test_invalid_file_falls_back_to_builtin(self, tmp_path):
        path = tmp_path / "rules.json"
        path.write_text("{not-json", encoding="utf-8")
        engine = RuleEngine(storage_path=path)
        assert any(rule["name"] == "usb-timeout" for rule in engine.list_rules())

    def test_saved_payload_has_expected_shape(self, tmp_path):
        path = tmp_path / "rules.json"
        engine = RuleEngine(storage_path=path)
        engine.add_rule("shape", "io_error", "检查 I/O")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert {"name", "match", "suggestion"} <= set(data[0].keys())
