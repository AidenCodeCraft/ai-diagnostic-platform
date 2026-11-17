"""复合提问拆分（split_query_units）与多问题检索（process_multi_query）。"""

from app.services.chat.query_preprocessor import process_multi_query, split_query_units
from app.services.rag.rag_prompt import RAG_STRICT_SYSTEM_PROMPT


class TestSplitQueryUnits:
    def test_numbered_multi_questions_split_and_followup_merged(self):
        """用户场景：1、…？2、…？如果…？ → 两个单元，追问并入第二问。"""
        text = (
            "1、如何判断设备的设备版本号？"
            "2、L10的GPS上报时间间隔可以进行修改嘛？如果可以修改在哪里修改呢？"
        )
        units = split_query_units(text)
        assert units == [
            "如何判断设备的设备版本号",
            "L10的GPS上报时间间隔可以进行修改嘛？如果可以修改在哪里修改呢",
        ]

    def test_followup_sentence_merges_into_single_unit(self):
        """用户场景：单问 + 追问是一个问题，不拆散（拆散会稀释检索词）。"""
        text = "L10的GPS上报时间间隔可以进行修改嘛？如果可以修改在哪里修改呢？"
        assert split_query_units(text) == [
            "L10的GPS上报时间间隔可以进行修改嘛？如果可以修改在哪里修改呢",
        ]

    def test_independent_unnumbered_questions_split(self):
        text = "如何判断设备版本号？L10的GPS间隔能修改吗？"
        assert split_query_units(text) == [
            "如何判断设备版本号",
            "L10的GPS间隔能修改吗",
        ]

    def test_numbering_prefix_stripped(self):
        assert split_query_units("2. L10的GPS间隔能修改吗？") == ["L10的GPS间隔能修改吗"]

    def test_decimal_version_not_stripped_as_numbering(self):
        assert split_query_units("2.5版本如何升级？") == ["2.5版本如何升级"]


class TestProcessMultiQuery:
    def test_retrieves_per_unit_and_merges_results(self):
        calls: list = []

        def search_fn(term: str, page_size: int):
            calls.append(term)
            if "版本号" in term:
                return {"items": [{"id": 1, "title": "版本号说明", "relevance_score": 0.9, "snippet": ""}]}
            if "间隔" in term:
                return {"items": [{"id": 2, "title": "GPS上传间隔", "relevance_score": 0.8, "snippet": ""}]}
            return {"items": []}

        result = process_multi_query(
            "1、如何判断设备的设备版本号？2、L10的GPS上报时间间隔可以进行修改嘛？",
            search_fn,
        )
        ids = {i["id"] for i in result.items}
        assert {1, 2} <= ids  # 两个子问题各自的文档都被召回
        assert result.matched_layer == "多问题检索"
        # 每个子问题都被独立检索过
        assert any("版本号" in t for t in calls)
        assert any("间隔" in t for t in calls)

    def test_single_unit_falls_back_to_plain_process(self):
        def search_fn(term: str, page_size: int):
            return {"items": [{"id": 7, "title": "GPS", "relevance_score": 0.9, "snippet": ""}]}

        result = process_multi_query("L10的GPS上报时间间隔可以修改吗？", search_fn)
        assert result.matched_layer != "多问题检索"
        assert any(i["id"] == 7 for i in result.items)

    def test_partial_match_not_contagious_across_units(self):
        """一个单元弱匹配不拖累整体：仅当全部单元都是部分匹配才置位。"""

        def search_fn(term: str, page_size: int):
            if "GPS" in term:
                return {"items": [{"id": 1, "title": "GPS手册", "relevance_score": 0.9, "snippet": "GPS"}]}
            return {"items": [{"id": 2, "title": "无关", "relevance_score": 0.5, "snippet": ""}]}

        result = process_multi_query("1、GPS？2、上报时间间隔可以进行修改吗？", search_fn)
        assert result.items
        assert result.is_partial_match is False


class TestRagPromptMultiQuestionRule:
    def test_prompt_requires_answering_every_sub_question(self):
        """回归护栏：提示词必须包含多子问题逐条作答规则。"""
        assert "逐条回答全部子问题" in RAG_STRICT_SYSTEM_PROMPT
        assert "铁则 4.5" in RAG_STRICT_SYSTEM_PROMPT
