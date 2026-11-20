"""原始 RRF 分暴露测试（跨层可比分数）。"""

from types import SimpleNamespace

from app.services.chat.query_preprocessor import QueryPreprocessor
from app.services.knowledge.section_search import SectionChunk, rank_sections


def _chunk(doc_id, section, body):
    return SectionChunk(
        doc_id=doc_id,
        chunk_no=0,
        title=f"doc{doc_id}",
        section=section,
        content=body,
        index_text=f"{section}\n{body}",
        key=f"{doc_id}:{section}:0",
        content_hash=f"h{doc_id}{section}",
    )


def _chunks():
    return [
        _chunk(1, "进出站", "进入站点 Enter station Rang index 后面数字表示首站 关键字 搜索"),
        _chunk(2, "客流", "客流累计上报逻辑 开门到关门上报开关门客流"),
        _chunk(3, "超速", "超速报警间隔时间 连续上报"),
    ]


def test_rank_sections_returns_raw_score_when_requested():
    chunks = _chunks()

    plain = rank_sections(chunks, query="进出站 关键字")
    with_raw = rank_sections(chunks, query="进出站 关键字", with_raw=True)

    assert len(plain[0]) == 2
    assert len(with_raw[0]) == 3
    # 排名第一的归一化分恒为 1.0，原始分才是可比较的
    assert with_raw[0][1] == 1.0
    assert 0 < with_raw[0][2] < 1.0
    # 原始分单调不增
    raw_scores = [raw for _, _, raw in with_raw]
    assert raw_scores == sorted(raw_scores, reverse=True)


def test_rank_score_prefers_raw_fusion_score():
    normalized_only = {"relevance_score": 1.0}
    with_raw = {"relevance_score": 1.0, "fusion_score": 0.0164}

    assert QueryPreprocessor._rank_score(normalized_only) == 1.0
    assert QueryPreprocessor._rank_score(with_raw) == 0.0164


def test_rank_score_falls_back_on_bad_value():
    assert QueryPreprocessor._rank_score({"fusion_score": "oops", "relevance_score": 0.7}) == 0.7
    assert QueryPreprocessor._rank_score({}) == 0.0
