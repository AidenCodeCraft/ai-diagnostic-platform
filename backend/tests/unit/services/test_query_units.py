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
        assert result.unit_count == 2
        # 每个子问题都被独立检索过
        assert any("版本号" in t for t in calls)
        assert any("间隔" in t for t in calls)

    def test_each_unit_top_docs_survive_merge_cut(self, monkeypatch):
        """回归（用户场景）：复合提问中子问题 1 的答案文档排在单元内第 6 名，
        不得被子问题 2 的高分文档挤出下游条数截断。

        此前合并结果按全局分数排序只保留 8 条、组装 Prompt 时再截 6 条，
        「设备端」（版本号答案文档）被挤到第 7 名后整体拒答。
        """
        import app.services.chat.query_preprocessor as qp

        def fake_process(query, search_fn=None, **kwargs):
            if "版本号" in query:
                items = [
                    {"id": 100 + i, "title": f"干扰{i}", "relevance_score": 0.10 - 0.001 * i, "snippet": ""}
                    for i in range(5)
                ]
                items.append({"id": 17, "title": "设备端", "relevance_score": 0.032, "snippet": ""})
            else:
                items = [
                    {"id": 200 + i, "title": f"其他{i}", "relevance_score": 0.09 - 0.001 * i, "snippet": ""}
                    for i in range(6)
                ]
            return qp.SearchResult(
                items=items, matched_layer="意图搜索", matched_term="本号",
                total_attempted=1, is_partial_match=True,
            )

        class StubPreprocessor:
            process = staticmethod(fake_process)

        monkeypatch.setattr(qp, "get_preprocessor", lambda: StubPreprocessor())

        q = (
            "1、如何判断设备的设备版本号？"
            "2、L10的GPS上报时间间隔可以进行修改嘛？如果可以修改在哪里修改呢？"
        )
        result = qp.process_multi_query(q, lambda term, size: {"items": []})

        ids = {i["id"] for i in result.items}
        # 每个单元的前 6 条（与单问题检索等量的预算）都在合并结果里
        assert {100, 101, 102, 103, 104, 17} <= ids
        assert {200, 201, 202, 203, 204, 205} <= ids
        assert any(i["id"] == 17 for i in result.items)

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


class TestRetrieveKnowledgeUnitBudget:
    def test_compound_question_answer_doc_reaches_prompt(self, db_session, monkeypatch):
        """用户场景回归：复合提问里子问题 1 的答案文档（「设备端」，合并后第 7 名）
        必须进入组装 Prompt 的检索结果——此前条数截断只保留 6 条，把它挤掉后，
        严格 RAG 提示词判定全部子问题无依据，输出整体拒答。"""
        from app.services.chat import diagnostic_chat_agent as dca
        from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent
        from app.services.chat.query_preprocessor import SearchResult

        agent = DiagnosticChatAgent(db_session, "mock")

        class FakeDoc:
            content = "## 日志搜索版本号\n\n使用关键字 master_start 检索版本号。"

        class FakeKnowledge:
            def get(self, doc_id):
                return FakeDoc()

            def _extract_snippet_info(self, content, term):
                return {
                    "snippet": content,
                    "section_title": "日志搜索版本号",
                    "section_key": "logver",
                    "start_line": 1,
                    "end_line": 3,
                }

        monkeypatch.setattr(agent, "knowledge", FakeKnowledge())

        # 复现修复前的合并排序：单元 2 的 6 条文档分数更高排在前面，
        # 子问题 1 的答案文档「设备端」落到第 7 名
        merged_items = [
            {"id": 200 + i, "title": f"其他{i}", "relevance_score": 0.09 - 0.001 * i, "snippet": ""}
            for i in range(6)
        ]
        merged_items.append({"id": 17, "title": "设备端", "relevance_score": 0.032, "snippet": ""})
        merged_items.append({"id": 31, "title": "JT808", "relevance_score": 0.03, "snippet": ""})

        monkeypatch.setattr(
            dca, "process_multi_query",
            lambda **kwargs: SearchResult(
                items=merged_items, matched_layer="多问题检索", matched_term="本号",
                total_attempted=2, is_partial_match=True, unit_count=2,
            ),
        )

        q = (
            "1、如何判断设备的设备版本号？"
            "2、L10的GPS上报时间间隔可以进行修改嘛？如果可以修改在哪里修改呢？"
        )
        context, refs = agent._retrieve_knowledge(q, {})

        assert context, "复合提问不应检索为空"
        assert any(r["title"] == "设备端" for r in refs), (
            "子问题 1 的答案文档被条数截断挤出 Prompt"
        )
