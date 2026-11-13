"""知识库标准化：模板 / 分节 / 规范化 / 校验 / 格式化预览。"""

from app.services.knowledge.section_parser import SectionParser
from app.services.knowledge.normalizer import Normalizer
from app.services.knowledge.validator import Validator
from app.services.knowledge.format_service import KnowledgeFormatService
from app.services.knowledge.templates import get_template, list_templates, guess_section_key

CASE_MD = """# 潜江 D3C 紧急报警上传异常

## 原因

上报司机手动命令:1 后平台下发 9206 文件上传，录像未写盘导致 -5007

## 现象

潜江的 D3C 设备，同样版本，有的车“紧急报警”上传视频，有的不上传

## 特征点

城市: 潜江
设备类型: D3C
版本: V2.1

## 处理结果

平台处理
"""

CASE_MD_VALID = (
    CASE_MD
    + "\n\n## 日志特征\n\n### 关键词\n\n- 紧急报警\n- 9206\n\n### 正则\n\n- (?i)9206\n"
)


class TestTemplates:
    def test_case_template_sections(self):
        template = get_template("case")
        assert template is not None
        keys = [s.key for s in template.sections]
        assert "symptom" in keys
        assert "root_cause" in keys
        assert "log_signature" in keys

    def test_list_templates_four_types(self):
        assert len(list_templates()) == 4

    def test_guess_section_key(self):
        assert guess_section_key("现象") == "symptom"
        assert guess_section_key("日志特征") == "log_signature"
        assert guess_section_key("不存在的章节") == ""


class TestSectionParser:
    def test_parse_case_sections_with_line_ranges(self):
        sections = SectionParser.parse(CASE_MD, "case")
        by_key = {s.section_key: s for s in sections}
        for key in ("symptom", "features", "root_cause", "solution"):
            assert key in by_key, list(by_key)
        symptom = by_key["symptom"]
        assert symptom.start_line > 0
        assert symptom.end_line >= symptom.start_line
        assert "潜江" in symptom.content

    def test_parse_free_form_fallback(self):
        sections = SectionParser.parse("没有标题的纯文本内容", "code_logic")
        assert len(sections) == 1
        assert sections[0].section_key == "body"


class TestNormalizer:
    def test_reorder_and_profile(self):
        result = Normalizer().normalize(CASE_MD, "case")
        content = result.normalized_content
        assert content.index("## 现象") < content.index("## 特征点") < content.index("## 原因") < content.index("## 处理结果")
        assert "潜江" in str(result.profile_draft["symptom"])
        assert result.features.get("城市") == "潜江"
        assert result.features.get("设备类型") == "D3C"
        assert "9206" in result.suggested_keywords

    def test_idempotent(self):
        first = Normalizer().normalize(CASE_MD, "case").normalized_content
        second = Normalizer().normalize(first, "case").normalized_content
        assert first == second

    def test_log_signature_parsed(self):
        result = Normalizer().normalize(CASE_MD_VALID, "case")
        assert "9206" in result.profile_draft["log_keywords"]
        assert result.profile_draft["log_patterns"] == ["(?i)9206"]


class TestValidator:
    @staticmethod
    def _validate(md: str, doc_type: str = "case"):
        result = Normalizer().normalize(md, doc_type)
        return Validator().validate(
            doc_type, result.sections, result.profile_draft, image_count=0,
        )

    def test_valid_case_active(self):
        validation = self._validate(CASE_MD_VALID)
        assert validation.status_hint == "active"
        assert not validation.has_errors
        assert validation.quality_score >= 60

    def test_missing_required_draft(self):
        md = CASE_MD_VALID.replace("## 处理结果", "## 备注")
        validation = self._validate(md)
        assert validation.status_hint == "draft"
        assert any(i.code == "MISSING_REQUIRED_SECTION" for i in validation.issues)

    def test_invalid_regex_error(self):
        md = CASE_MD_VALID.replace("- (?i)9206", "- [unclosed")
        validation = self._validate(md)
        assert any(i.code == "INVALID_REGEX" for i in validation.issues)

    def test_unstructured_content_stays_active(self):
        validation = self._validate("设备不上传视频", "faq")
        assert validation.status_hint == "active"
        assert any(i.code == "UNSTRUCTURED_CONTENT" for i in validation.issues)

    def test_free_form_document_active(self):
        validation = self._validate("一段普通笔记", "note")
        assert validation.status_hint == "active"


class TestFormatPreview:
    def test_preview_contains_normalized_and_profile(self):
        data = KnowledgeFormatService().preview(CASE_MD, "case")
        assert data["normalized_content"]
        assert data["profile_draft"]["symptom"]
        assert data["template"]["doc_type"] == "case"
        assert "issues" in data
        assert "quality_score" in data
        assert "notes" in data


# 用户实际反馈的自由格式内容（基础知识）
KNOWLEDGE_MD = """# 概要说明

- 该文档由硬件研发和测试统一维护更新；
- 该文档针对现场实施人员和相关的测试人员；
- 该文档适用于FC09 / FC10 / FC12 / L13V / L13C / D3C设备

|术语|解释|
|---|---|
|VO通道|Video Output, 视频预览界面,每一个视频显示通道|
|OSD|叠加到视频上的文字信息|
|回显|带OSD的通道状态|
|直通|不带OSD的通道状态, 纯视频画面|
|IPC|网络摄像头|
|AHD|模拟摄像头|
"""


class TestFreeFormKnowledge:
    def test_auto_promotes_h1_to_sections(self):
        result = Normalizer().normalize(KNOWLEDGE_MD, "knowledge")
        assert "## 概要说明" in result.normalized_content
        assert any(section.level == 2 for section in result.sections)
        assert result.notes

    def test_validator_no_unstructured_warning_for_free_form(self):
        result = Normalizer().normalize(KNOWLEDGE_MD, "knowledge")
        validation = Validator().validate(
            "knowledge", result.sections, result.profile_draft,
        )
        assert not validation.has_errors
        assert validation.status_hint == "active"
        assert not any(
            issue.code == "UNSTRUCTURED_CONTENT" for issue in validation.issues
        )
        assert validation.quality_score >= 80

    def test_no_heading_content_gets_body_section(self):
        result = Normalizer().normalize("设备适用于 FC09 / FC10 / FC12 等型号。", "knowledge")
        assert "## 正文" in result.normalized_content
        assert result.notes

    def test_free_form_normalize_is_idempotent(self):
        first = Normalizer().normalize(KNOWLEDGE_MD, "knowledge")
        second = Normalizer().normalize(first.normalized_content, "knowledge")
        assert second.normalized_content == first.normalized_content
        assert second.notes == []

    def test_preview_reports_notes_and_no_warning(self):
        data = KnowledgeFormatService().preview(KNOWLEDGE_MD, "knowledge")
        assert "## 概要说明" in data["normalized_content"]
        assert data["notes"]
        assert not any(
            issue["code"] == "UNSTRUCTURED_CONTENT" for issue in data["issues"]
        )
        assert data["quality_score"] >= 80
