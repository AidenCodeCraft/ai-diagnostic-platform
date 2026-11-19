"""章节切分：标题切分、长节切窗、目录/前言过滤。"""

from app.services.knowledge.sections import (
    MAX_SECTION_CHARS,
    is_navigation_heading,
    looks_like_toc,
    split_markdown_sections,
)


def test_splits_by_headings():
    content = "# 现象\nGPS 不上报\n\n## 排查\n1. 检查天线\n"
    sections = split_markdown_sections(content)
    assert [heading for heading, _ in sections] == ["现象", "排查"]


def test_long_section_is_windowed_by_paragraph():
    paragraph = "这是一段比较长的说明文字。" * 40      # ~520 字
    content = "# 长章节\n\n" + "\n\n".join([paragraph] * 4)

    sections = split_markdown_sections(content)

    assert len(sections) > 1, "超长小节必须切窗，否则 BM25 被长度归一化稀释"
    assert all(heading == "长章节" for heading, _ in sections)
    assert max(len(body) for _, body in sections) <= MAX_SECTION_CHARS + 200


def test_drops_toc_by_heading():
    content = "# 目录\n- [现象](#现象)\n- [排查](#排查)\n\n# 现象\nGPS 不上报\n"
    headings = [heading for heading, _ in split_markdown_sections(content)]
    assert "目录" not in headings
    assert "现象" in headings


def test_drops_preface_and_change_log():
    content = "# 前言\n本文说明 L10 的排查流程。\n\n# 修订记录\n| 版本 | 日期 |\n\n# 现象\nGPS 不上报\n"
    headings = [heading for heading, _ in split_markdown_sections(content)]
    assert headings == ["现象"]


def test_drops_toc_like_body_without_toc_heading():
    body = "\n".join(["- [现象](#x)", "- [排查](#y)", "- [附录](#z)", "- [FAQ](#q)"])
    content = f"# 导读目录\n{body}\n\n# 现象\nGPS 不上报\n"
    headings = [heading for heading, _ in split_markdown_sections(content)]
    assert headings == ["现象"], "正文本身像目录时也要丢弃，避免污染检索"


def test_keeps_normal_bullet_lists():
    content = "# 排查\n- 检查天线\n- 检查固件\n- 检查供电\n"
    assert looks_like_toc("# 排查\n- 检查天线\n- 检查固件\n- 检查供电") is False
    assert len(split_markdown_sections(content)) == 1


def test_navigation_can_be_disabled():
    content = "# 目录\n- [现象](#现象)\n- [排查](#排查)\n- [附录](#a)\n\n# 现象\nGPS 不上报\n"
    headings = [heading for heading, _ in split_markdown_sections(content, drop_navigation=False)]
    assert "目录" in headings


def test_is_navigation_heading_variants():
    for heading in ("目录", "Contents", "表目录", "前言", "序言", "修订记录", "免责声明"):
        assert is_navigation_heading(heading) is True, heading
    for heading in ("现象", "4G 注册失败", "FAQ", "排查步骤"):
        assert is_navigation_heading(heading) is False, heading
