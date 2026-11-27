"""跨文档同内容去重（A3）。"""

from types import SimpleNamespace

from app.services.knowledge.knowledge_service import (
    dedupe_by_content_hash,
    dedupe_pairs_by_content_hash,
)


def chunk(hash_, doc_id=1, section="现象"):
    return SimpleNamespace(content_hash=hash_, doc_id=doc_id, section=section)


def test_dedupes_same_content_across_documents():
    chunks = [chunk("h1", 36), chunk("h1", 11), chunk("h2", 11)]

    unique = dedupe_by_content_hash(chunks)

    assert len(unique) == 2
    assert unique[0].doc_id == 36, "保留排名靠前的那条"
    assert unique[1].content_hash == "h2"


def test_chunks_without_hash_are_kept():
    chunks = [chunk(""), chunk("")]
    assert len(dedupe_by_content_hash(chunks)) == 2


def test_pairs_version_keeps_score_for_first_occurrence():
    pairs = [(chunk("h1", 36), 0.9), (chunk("h1", 11), 0.8), (chunk("h3", 11), 0.5)]

    result = dedupe_pairs_by_content_hash(pairs)

    assert [c.doc_id for c, _ in result] == [36, 11]
    assert [s for _, s in result] == [0.9, 0.5]
