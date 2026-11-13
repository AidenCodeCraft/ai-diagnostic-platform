"""知识库模板骨架 / AI 润色服务。"""

from app.services.knowledge.format_service import KnowledgeFormatService
from app.services.knowledge.polish_service import KnowledgePolishService
from app.services.knowledge.templates import CASE_SKELETON, list_templates

ROUGH_CASE = """设备是D3C，版本V2.1，城市潜江。
紧急报警上传视频有些车成功有些失败。
原因应该是录像没写盘，平台下发9206后返回-5007。
处理办法：确认司机是否手动触发命令，检查写盘状态。
日志里能搜到 9206 和 -5007。
"""

VALID_POLISHED = """## 现象

潜江 D3C（V2.1）设备紧急报警上传视频，部分车辆成功、部分失败。

## 特征点

- 城市：潜江
- 设备类型：D3C
- 版本：V2.1

## 原因

平台下发 9206 后录像未写盘，返回 -5007。

## 处理结果

确认司机是否手动触发命令，并检查写盘状态与 9206 下发链路。

## 日志特征

### 关键词

- 9206
- -5007
"""


class _FakeProvider:
    def __init__(self, reply: str):
        self.reply = reply
        self.messages = None

    def health_check(self) -> bool:
        return True

    def chat(self, messages):
        self.messages = messages
        return self.reply


class TestTemplateAssets:
    def test_templates_have_skeleton_guide_example(self):
        templates = list_templates()
        assert len(templates) == 4
        for item in templates:
            assert item["skeleton"].strip(), item["doc_type"]
            assert item["guide"].strip(), item["doc_type"]
            assert item["example"].strip(), item["doc_type"]

    def test_case_skeleton_contains_required_sections(self):
        case = next(t for t in list_templates() if t["doc_type"] == "case")
        skeleton = case["skeleton"]
        for title in ("现象", "原因", "处理结果", "日志特征"):
            assert f"## {title}" in skeleton

    def test_skeleton_preview_warns_placeholder(self):
        data = KnowledgeFormatService().preview(CASE_SKELETON, "case")
        codes = [issue["code"] for issue in data["issues"]]
        assert "PLACEHOLDER_CONTENT" in codes


class TestPolishProviderResolution:
    def test_prefers_admin_default_model(self, monkeypatch):
        import app.services.knowledge.provider_registry as registry_module

        monkeypatch.setattr(registry_module, "_load_admin_config", lambda: {
            "llm": {
                "models": [
                    {"model": "model-backup", "api_key": "sk-backup"},
                    {"model": "deepseek-v4-flash", "api_key": "sk-main", "isDefault": True},
                ],
            },
        })

        calls = []

        class _HealthyProvider:
            def health_check(self):
                return True

        def _fake_get(self, name=None):
            calls.append(name)
            return _HealthyProvider()

        monkeypatch.setattr(registry_module.ProviderRegistry, "get_provider", _fake_get)
        provider = KnowledgePolishService()._default_provider()

        assert provider is not None
        assert calls[0] == "deepseek-v4-flash"

    def test_returns_none_when_only_mock_available(self, monkeypatch):
        import app.services.knowledge.provider_registry as registry_module
        from app.services.providers.mock_provider import MockProvider

        monkeypatch.setattr(registry_module, "_load_admin_config", lambda: {})
        monkeypatch.setattr(
            registry_module.ProviderRegistry,
            "get_provider",
            lambda self, name=None: MockProvider(),
        )
        assert KnowledgePolishService()._default_provider() is None


class TestKnowledgePolish:
    def test_rule_fallback_when_llm_unavailable(self, monkeypatch):
        monkeypatch.setattr(KnowledgePolishService, "_default_provider", lambda self: None)
        result = KnowledgePolishService().polish(ROUGH_CASE, "case", "D3C 上传异常")

        assert result["source"] == "rule"
        assert result["polished_content"]
        assert any("回退" in note or "规则" in note for note in result["notes"])
        # 规则回退不会臆造模板章节，但不应产生 error 级问题
        assert not any(i["level"] == "error" for i in result["issues"])

    def test_llm_polish_success(self):
        provider = _FakeProvider(VALID_POLISHED)
        result = KnowledgePolishService(provider=provider).polish(
            ROUGH_CASE, "case", "D3C 上传异常",
        )

        assert result["source"] == "llm"
        assert "## 现象" in result["polished_content"]
        assert provider.messages is not None
        assert result["quality_score"] > 0

    def test_llm_output_missing_key_tokens_falls_back(self):
        broken = VALID_POLISHED.replace("9206", "命令").replace("-5007", "错误码")
        result = KnowledgePolishService(provider=_FakeProvider(broken)).polish(
            ROUGH_CASE, "case", "D3C 上传异常",
        )
        assert result["source"] == "rule"
        assert any("一致性校验" in note for note in result["notes"])

    def test_numbers_multiple_free_form_paragraphs(self):
        content = "第一条说明：设备适用 FC09。\n\n第二条说明：设备适用 L13C。"
        numbered = KnowledgePolishService._number_parallel_items(content, "knowledge")
        assert numbered.startswith("1. ")
        assert "\n\n2. " in numbered

    def test_numbers_multiple_free_form_sections(self):
        content = "## 安装要求\n\n内容A\n\n## 使用限制\n\n内容B"
        numbered = KnowledgePolishService._number_parallel_items(content, "knowledge")
        assert "## 1. 安装要求" in numbered
        assert "## 2. 使用限制" in numbered

    def test_structured_template_keeps_sections(self):
        content = "## 现象\n\na\n\n## 原因\n\nb"
        assert KnowledgePolishService._number_parallel_items(content, "case") == content

    def test_rule_polish_numbers_parallel_content(self, monkeypatch):
        monkeypatch.setattr(KnowledgePolishService, "_default_provider", lambda self: None)
        content = "第一条说明：设备适用 FC09。\n\n第二条说明：设备适用 L13C。"
        result = KnowledgePolishService().polish(content, "knowledge")
        polished = result["polished_content"]
        assert "1. " in polished
        assert "2. " in polished

    def test_empty_content_raises(self):
        try:
            KnowledgePolishService().polish("   ", "case")
        except ValueError as exc:
            assert "内容为空" in str(exc)
        else:
            raise AssertionError("expected ValueError")
