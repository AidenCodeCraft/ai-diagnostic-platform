"""用户截图的现场证据：注入方式与歧义澄清抑制。

回归背景（2026-11-27）：用户上传日志截图问「这个日志中程序版本是多少？」，
截图里是 2.6.11.2，模型却照搬知识库示例 2.6.7.1G。根因有两个：
1. 前端流式请求漏传 image_ids，截图没绑定到会话；
2. 截图文本混在「知识库检索结果」里，被当成知识库示例，且仍先弹知识库条目澄清。
这里锁定后端的 2 个行为。
"""

from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent

KB_ITEMS = [{
    "id": 17,
    "key": "17:1. 日志搜索版本号:分析",
    "title": "设备端",
    "section": "1. 日志搜索版本号 > 分析",
    "snippet": "日志搜索版本号时，使用关键字 master_start 进行检索。",
    "relevance_score": 1.0,
}]

IMAGE_EVIDENCE = [{
    "image_id": 6,
    "path": "ocr",
    "text": "[2026-11-26 11:05:08] [MASTER_Start 0259] pri: 2.6.11.2_L3C_10",
}]


def _agent(db_session, image_evidence=None):
    agent = DiagnosticChatAgent(
        db_session, "mock", log_context={"image_evidence": image_evidence or []},
    )
    agent.knowledge.search = lambda *a, **k: {
        "items": list(KB_ITEMS), "total": 1, "page": 1, "page_size": 10,
    }
    return agent


def test_image_text_not_mixed_into_knowledge_context(db_session):
    agent = _agent(db_session, IMAGE_EVIDENCE)

    context, _ = agent._retrieve_knowledge(
        "这个日志中程序版本是多少？", {"sub_questions": []},
    )

    assert "2.6.11.2" not in context, "截图原文不应混进知识库检索结果"
    assert agent.image_evidence == IMAGE_EVIDENCE


def test_rag_prompt_prioritises_screenshot_value(db_session):
    agent = _agent(db_session, IMAGE_EVIDENCE)

    context, _ = agent._retrieve_knowledge(
        "这个日志中程序版本是多少？", {"sub_questions": []},
    )
    messages = agent._assemble_rag_mode(
        [], "这个日志中程序版本是多少？", context,
    )

    system_prompt = messages[0]["content"]
    user_prompt = messages[-1]["content"]
    assert "现场证据优先" in system_prompt
    assert "不得直接当作本次日志的实际值" in system_prompt
    assert "2.6.11.2" in user_prompt
    assert "截图 #6" in user_prompt


def test_ambiguity_clarification_skipped_when_screenshot_present(db_session):
    agent = _agent(db_session, IMAGE_EVIDENCE)
    agent._candidates = [
        {"doc_id": 17, "title": "设备端", "section": "关键字", "score": 1.0, "status": "active"},
        {"doc_id": 3, "title": "平台对接", "section": "作者", "score": 0.99, "status": "active"},
    ]

    assert agent._maybe_ask_ambiguity("这个日志中程序版本是多少？", []) is None


def test_ambiguity_still_asked_without_screenshot(db_session):
    agent = _agent(db_session)
    agent._candidates = [
        {"doc_id": 17, "title": "设备端", "section": "关键字", "score": 1.0, "status": "active"},
        {"doc_id": 3, "title": "平台对接", "section": "作者", "score": 0.99, "status": "active"},
    ]

    reply = agent._maybe_ask_ambiguity("这个日志中程序版本是多少？", [])

    assert reply is not None
