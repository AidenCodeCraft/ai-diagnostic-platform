"""章节级融合检索测试（BM25 + RRF；向量一路用伪造命中）。"""

from types import SimpleNamespace

import pytest

from app.models import KnowledgeDocument
from app.services.knowledge import knowledge_service as ks
from app.services.knowledge.section_search import (
    SectionBM25Index,
    build_section_chunks,
    corpus_signature,
    fuse_rrf,
    map_dense_hits,
    rank_sections,
)
from app.services.knowledge.sections import content_hash, split_markdown_sections


def _doc(doc_id, title, content, updated=None):
    return SimpleNamespace(id=doc_id, title=title, content=content, updated_at=updated)


def test_split_markdown_sections_basic():
    sections = split_markdown_sections("# 现象\n第一段内容\n\n## 处理\n第二段内容\n")
    assert [heading for heading, _ in sections] == ["现象", "现象 > 处理"]


def test_build_section_chunks_skips_short_sections():
    docs = [_doc(1, "标题", "# 一节\n" + "内容" * 20 + "\n\n## 目录\n短\n")]
    chunks = build_section_chunks(docs)

    assert [chunk.section for chunk in chunks] == ["一节"]
    assert chunks[0].key.startswith("1:一节:")


def test_corpus_signature_changes_with_update_time():
    a = [_doc(1, "t", "# x\n" + "内容" * 20, updated=SimpleNamespace(isoformat=lambda: "2026-01-01"))]
    b = [_doc(1, "t", "# x\n" + "内容" * 20, updated=SimpleNamespace(isoformat=lambda: "2026-01-02"))]
    assert corpus_signature(a) != corpus_signature(b)


def test_fuse_rrf_rewards_appearing_in_both_lists():
    fused = fuse_rrf([[0, 1], [1, 0]])
    assert fused[0] == pytest.approx(fused[1])
    fused2 = fuse_rrf([[0, 1], [1, 2]])
    assert fused2[1] > fused2[2]  # 同时出现在两路 → 名次更高


def test_map_dense_hits_aligns_by_content_hash():
    docs = [_doc(1, "标题", "# 一节\n" + "章节内容" * 10 + "\n")]
    chunks = build_section_chunks(docs)
    hit = {
        "id": 1,
        "title": "标题",
        "section": "一节",
        "content": chunks[0].content,
    }
    assert map_dense_hits(chunks, [hit]) == [0]

    stale = dict(hit, content="被改写的旧内容")
    assert map_dense_hits(chunks, [stale]) == []


def test_rank_sections_promotes_dense_hit_over_bm25_only():
    docs = [
        _doc(1, "GPS 说明", "# 定位\nGPS 不上报时检查天线与固件版本。\n"),
        _doc(2, "电源说明", "# 供电\n电压异常会导致设备反复重启。\n"),
    ]
    chunks = build_section_chunks(docs)
    index = SectionBM25Index()
    index.ensure(chunks, "sig")

    # 向量一路把「电源」章节排到第一
    dense = [{"id": 2, "title": "电源说明", "section": "供电", "content": chunks[1].content}]
    ranked = rank_sections(chunks, query="设备反复重启怎么办", dense_hits=dense, bm25_index=index)

    assert ranked
    assert ranked[0][0].doc_id == 2
    assert ranked[0][1] == 1.0


def test_rank_sections_without_dense_still_works():
    docs = [_doc(1, "GPS 说明", "# 定位\nGPS 不上报时检查天线与固件版本。\n")]
    chunks = build_section_chunks(docs)
    index = SectionBM25Index()
    index.ensure(chunks, "sig")

    ranked = rank_sections(chunks, query="GPS 不上报", dense_hits=[], bm25_index=index)
    assert [chunk.doc_id for chunk, _ in ranked] == [1]


@pytest.fixture(autouse=True)
def _reset_cache():
    ks.reset_section_index_cache()
    yield
    ks.reset_section_index_cache()


@pytest.fixture
def seeded_docs(db_session):
    docs = [
        KnowledgeDocument(
            title="L10 定位排查",
            content="# 现象\n设备 GPS 不上报，平台无位置。\n\n# 处理\n检查天线连接与固件版本。\n",
            status="active",
        ),
        KnowledgeDocument(
            title="L10 电源排查",
            content="# 现象\n设备反复重启。\n\n# 处理\n测量供电电压是否稳定。\n",
            status="active",
        ),
    ]
    db_session.add_all(docs)
    db_session.commit()
    for doc in docs:
        db_session.refresh(doc)
    return docs


def test_search_returns_sections_when_requested(db_session, seeded_docs):
    service = ks.KnowledgeService(db_session)

    result = service.search("GPS 不上报怎么处理", page_size=5, sections=True)

    assert result["items"], "应命中至少一个章节"
    top = result["items"][0]
    assert top["section"] in ("现象", "处理")
    assert top["key"].startswith(f"{top['id']}:")
    assert top["relevance_score"] == 1.0


def test_search_dedupes_documents_by_default(db_session, seeded_docs):
    service = ks.KnowledgeService(db_session)

    result = service.search("设备 排查 处理", page_size=5)

    ids = [item["id"] for item in result["items"]]
    assert len(ids) == len(set(ids)), "默认应按文档去重"
    assert all("section" in item for item in result["items"])


def test_search_empty_query_returns_empty(db_session, seeded_docs):
    service = ks.KnowledgeService(db_session)
    assert service.search("   ")["items"] == []


class TestPlaceholderSections:
    """作者留的「（草稿未提供）」空壳章节不能进检索语料。

    真实案例：文档《TMP》里两节正文就是「（草稿未提供）」，
    向量检索把它排到第 1，回答只能照抄一句「知识库未提供」。
    """

    def _doc(self, content: str):
        from types import SimpleNamespace

        return SimpleNamespace(id=1, title="TMP", content=content)

    def test_placeholder_section_is_excluded(self):
        from app.services.knowledge.section_search import build_section_chunks

        content = (
            "## 1. 下载文件分析\n\n### 分析\n\n（草稿未提供）\n\n**作者:** 隆昌林 2026.2.28\n\n"
            "## 2. 关键字解释\n\n| `FileListUpgradeProc end` | 下载结束打印 |\n"
        )
        chunks = build_section_chunks([self._doc(content)])
        bodies = " ".join(c.content for c in chunks)
        assert "草稿未提供" not in bodies
        assert "FileListUpgradeProc end" in bodies

    def test_pending_marks_are_excluded(self):
        from app.services.knowledge.section_search import build_section_chunks

        content = "## 1. 待补充\n\n待补充\n\n## 2. 真内容\n\n日志搜索使用 `master_start` 关键字。\n"
        chunks = build_section_chunks([self._doc(content)])
        assert len(chunks) == 1
        assert "master_start" in chunks[0].content
