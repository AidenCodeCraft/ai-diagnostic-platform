"""检索歧义：多个章节得分接近时生成澄清选项。"""

from app.services.chat.retrieval_ambiguity import find_ambiguous_candidates

QUERY = "进出站日志中搜索什么"


def _candidate(doc_id, title, section, score, status="active"):
    return {
        "doc_id": doc_id, "title": title, "section": section,
        "score": score, "status": status,
    }


class TestRetrievalAmbiguity:
    def test_close_scores_trigger_clarification(self):
        candidates = [
            _candidate(1, "线路", "5. 查看设备是否有进出站", 1.0),
            _candidate(2, "平台对接", "2. 查看平台连接信息", 0.95),
        ]
        result = find_ambiguous_candidates(candidates, QUERY)
        assert len(result) == 2
        assert "线路" in result[0].option_label()

    def test_clear_winner_no_clarification(self):
        candidates = [
            _candidate(1, "线路", "5. 查看设备是否有进出站", 1.0),
            _candidate(2, "平台对接", "2. 查看平台连接信息", 0.4),
        ]
        assert find_ambiguous_candidates(candidates, QUERY) == []

    def test_same_document_is_not_ambiguous(self):
        candidates = [
            _candidate(1, "FAQ", "5. 查看设备是否有进出站", 1.0),
            _candidate(1, "FAQ", "6. 手动触发报站", 0.98),
        ]
        assert find_ambiguous_candidates(candidates, QUERY) == []

    def test_user_already_named_section(self):
        candidates = [
            _candidate(1, "线路", "5. 查看设备是否有进出站", 1.0),
            _candidate(2, "平台对接", "2. 查看平台连接信息", 0.95),
        ]
        query = "线路 · 5. 查看设备是否有进出站"
        assert find_ambiguous_candidates(candidates, query) == []

    def test_draft_label(self):
        candidates = [
            _candidate(1, "FAQ", "5. 查看设备是否有进出站", 1.0, status="draft"),
            _candidate(2, "线路", "关键字", 0.96),
        ]
        labels = [c.option_label() for c in find_ambiguous_candidates(candidates, QUERY)]
        assert labels[0].endswith("（草稿）")

    def test_weak_matches_ignored(self):
        candidates = [
            _candidate(1, "A", "x", 0.1),
            _candidate(2, "B", "y", 0.09),
        ]
        assert find_ambiguous_candidates(candidates, QUERY) == []
