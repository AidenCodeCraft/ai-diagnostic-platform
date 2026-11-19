"""日志证据注入对话上下文（P1 步骤 5）。"""

from datetime import datetime

from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent

KB_ITEMS = [{
    "id": 1,
    "key": "1:GPS 不上报排查:0",
    "title": "GPS 排查",
    "section": "GPS 不上报排查",
    "snippet": "先看模块 NL668_4G 是否注册，可执行 AT+CGDCONT? 检查 PDP 上下文。",
    "relevance_score": 1.0,
}]

LOG = "\n".join([
    "[2026-08-02 14:19:58]  [APP] pri:  heartbeat ok",
    "[2026-08-02 14:20:00]  [NL668_4G] pri:  AT+CGDCONT? returned empty",
    "[2026-08-02 14:20:05]  [NL668_4G] pri:  NMEA no signal, retry",
]) + "\n"


def _agent(db_session, log_context=None):
    agent = DiagnosticChatAgent(db_session, "mock", log_context=log_context)
    agent.knowledge.search = lambda *a, **k: {"items": list(KB_ITEMS), "total": 1, "page": 1, "page_size": 10}
    return agent


def test_evidence_is_injected_into_knowledge_context(db_session):
    agent = _agent(db_session, log_context={
        "data": LOG.encode("utf-8"),
        "start": datetime(2026, 8, 2, 14, 15),
        "end": datetime(2026, 8, 2, 14, 25),
        "window_label": "14:20 附近",
    })

    context, references = agent._retrieve_knowledge("GPS 不上报怎么排查", {"sub_questions": []})

    assert "## 日志命中" in context
    assert "行 " in context
    assert agent.log_evidence is not None
    assert agent.log_evidence["patterns"]
    assert references, "知识库引用仍应保留（编号与上下文一致）"


def test_no_log_context_keeps_previous_behaviour(db_session):
    agent = _agent(db_session)

    context, references = agent._retrieve_knowledge("GPS 不上报怎么排查", {"sub_questions": []})

    assert "## 日志命中" not in context
    assert agent.log_evidence is None
    assert references


def test_zero_hit_log_does_not_inject_empty_block(db_session):
    agent = _agent(db_session, log_context={
        "data": b"[2026-08-02 14:20:00]  [APP] pri:  heartbeat ok\n",
        "start": datetime(2026, 8, 2, 14, 15),
        "end": datetime(2026, 8, 2, 14, 25),
        "window_label": "14:20 附近",
    })

    context, _ = agent._retrieve_knowledge("GPS 不上报怎么排查", {"sub_questions": []})

    assert "## 日志命中" not in context
    assert "关键点" in agent.log_evidence_summary
