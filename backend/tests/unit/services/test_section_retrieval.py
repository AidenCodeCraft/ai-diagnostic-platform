"""章节级检索：长文档中的正确小节必须排到前面，草稿按需参与。"""

from app.models import KnowledgeDocument
from app.services.knowledge.knowledge_service import KnowledgeService
from app.services.knowledge.sections import split_markdown_sections

FAQ = """# 1. 无关的日志说明
日志搜索是常见手段，日志搜索方法见下，日志搜索时请注意时间范围。
日志搜索告警、日志搜索平台连接、日志搜索录像，这些都与进出站无关。
日志搜索还可以用于排查录像、平台连接、GPS 等问题，属于通用说明。

# 5. 查看设备是否有进出站
现象：车辆在运行途中，有站点不报站的情况。
分析：先查看设备是否有进出站，再查看设备 GPS 是否正常。
关键字：可搜索如下关键字，下面关键字表示进入了站点

|关键字|解释|
| -------- | -------- |
| Enter station Rang index | 后面数字表明设备进入首站，从0开始数 |
| enStationState | 后面数字0代表进站，1表示出站 |
| szChStationName | 当前进入站点名 |
"""

NOISE = """# 1. 实际运行方向与当前线路运行方向相反
现象：设备经过站点未报站，反方向经过两个站后自动切换方向。
分析：日志搜索。
关键字：`auto check change Out station reversal point`
"""


def _seed(db, status: str = "active"):
    faq = KnowledgeDocument(title="FAQ", content=FAQ, doc_type="case", status=status)
    noise = KnowledgeDocument(title="线路", content=NOISE, doc_type="faq", status="active")
    db.add_all([faq, noise])
    db.commit()
    return faq, noise


class TestSectionRetrieval:
    def test_exact_section_ranks_first(self, db_session):
        _seed(db_session)

        items = KnowledgeService(db_session).search(
            "进出站日志中搜索什么", page_size=5,
            include_drafts=True, return_sections=True,
        )["items"]

        assert items, "检索结果为空"
        assert items[0]["section"] == "5. 查看设备是否有进出站"
        assert items[0]["snippet"].startswith("## 5.")
        assert "enStationState" in items[0]["snippet"]

    def test_draft_only_when_requested(self, db_session):
        _seed(db_session, status="draft")
        service = KnowledgeService(db_session)

        active_only = service.search("进出站日志中搜索什么", page_size=5)["items"]
        assert all(item["title"] != "FAQ" for item in active_only)

        with_draft = service.search(
            "进出站日志中搜索什么", page_size=5, include_drafts=True,
        )["items"]
        assert any(item["title"] == "FAQ" for item in with_draft)


class TestSectionSplit:
    def test_split_by_headings(self):
        sections = split_markdown_sections("# A\ntext a\n## B\ntext b")
        assert [heading for heading, _ in sections] == ["A", "B"]

    def test_preamble_kept(self):
        sections = split_markdown_sections("前言\n\n# A\ntext")
        assert sections[0][0] == ""
        assert "前言" in sections[0][1]
