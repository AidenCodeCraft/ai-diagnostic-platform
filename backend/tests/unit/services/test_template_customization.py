"""知识模板格式说明/结构项的自定义与恢复。"""

import pytest

from app.core.config import settings
from app.services.knowledge import template_store
from app.services.knowledge.format_service import KnowledgeFormatService
from app.services.knowledge.template_store import reset_override, upsert_override
from app.services.knowledge.templates import get_template, list_templates


@pytest.fixture(autouse=True)
def isolated_template_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings, "KNOWLEDGE_TEMPLATE_FILE", str(tmp_path / "template_overrides.json"),
    )
    template_store._cache["mtime"] = None
    template_store._cache["data"] = {}
    yield
    template_store._cache["mtime"] = None
    template_store._cache["data"] = {}


class TestTemplateCustomization:
    def test_custom_guide_and_sections_take_effect(self):
        upsert_override("faq", {
            "guide": "自定义格式说明",
            "sections": [
                {"title": "问题", "key": "symptom", "level": "required"},
                {"title": "处理", "key": "solution", "level": "required"},
            ],
        })

        template = get_template("faq")
        assert template is not None
        assert template.guide == "自定义格式说明"
        assert [section.title for section in template.sections] == ["问题", "处理"]

        listed = next(t for t in list_templates() if t["doc_type"] == "faq")
        assert listed["is_customized"] is True
        assert listed["guide"] == "自定义格式说明"

        # 自定义必填章节参与校验
        preview = KnowledgeFormatService().preview("## 现象\n\n内容", "faq")
        codes = [issue["code"] for issue in preview["issues"]]
        assert "MISSING_REQUIRED_SECTION" in codes

    def test_custom_required_sections_apply_to_free_form(self):
        upsert_override("knowledge", {
            "sections": [
                {"title": "概念", "key": "concept", "level": "required"},
                {"title": "说明", "key": "detail", "level": "optional"},
            ],
        })
        preview = KnowledgeFormatService().preview("## 说明\n\n内容", "knowledge")
        codes = [issue["code"] for issue in preview["issues"]]
        assert "MISSING_REQUIRED_SECTION" in codes
        assert preview["status_hint"] == "draft"

        # 未分节的自由文本仍可发布（不强制套用自定义结构）
        free = KnowledgeFormatService().preview("一段未分节的自由文本", "knowledge")
        assert free["status_hint"] == "active"

    def test_reset_restores_builtin(self):
        upsert_override("faq", {"guide": "临时说明"})
        assert reset_override("faq") is True
        template = get_template("faq")
        assert template is not None
        assert template.guide != "临时说明"
        listed = next(t for t in list_templates() if t["doc_type"] == "faq")
        assert listed["is_customized"] is False

    def test_unknown_doc_type_rejected(self):
        try:
            upsert_override("unknown_type", {"guide": "x"})
        except ValueError as exc:
            assert "未知文档类型" in str(exc)
        else:
            raise AssertionError("expected ValueError")
