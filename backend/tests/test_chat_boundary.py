"""Chat/诊断 Agent 边界测试 + API 端到端测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════════
# DiagnosticChatAgent 边界测试
# ═══════════════════════════════════════════════════════════

def test_diagnostic_agent_sanitize(client):
    from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent
    db = client.app.state.db if hasattr(client.app.state, 'db') else None
    agent = DiagnosticChatAgent.__new__(DiagnosticChatAgent)
    # 测试清洗逻辑（不需要完整初始化）
    assert agent._sanitize("  hello\n\n\nworld  ") == "hello\n\nworld"
    assert agent._sanitize("\x00\x01\x02test") == "test"
    assert agent._sanitize("") == ""


def test_diagnostic_agent_should_refuse(client):
    from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent
    agent = DiagnosticChatAgent.__new__(DiagnosticChatAgent)
    assert agent._should_refuse("") is True
    assert agent._should_refuse("test") is True
    assert agent._should_refuse("123") is True
    assert agent._should_refuse("设备黑屏了") is False
    assert agent._should_refuse("你好，请问") is False


def test_diagnostic_agent_analyze_question_diagnostic():
    from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent
    agent = DiagnosticChatAgent.__new__(DiagnosticChatAgent)
    result = agent._analyze_question("设备黑屏了无法开机")
    assert result["is_diagnostic"] is True
    assert result["score"] >= 3
    assert len(result["matched_keywords"]) > 0


def test_diagnostic_agent_analyze_question_non_diagnostic():
    from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent
    agent = DiagnosticChatAgent.__new__(DiagnosticChatAgent)
    result = agent._analyze_question("你好")
    assert result["is_diagnostic"] is False
    assert result["is_simple"] is True


def test_diagnostic_agent_analyze_question_compound():
    from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent
    agent = DiagnosticChatAgent.__new__(DiagnosticChatAgent)
    result = agent._analyze_question("帮我分析日志里的kernel panic和USB timeout错误")
    assert result["is_diagnostic"] is True
    assert result["score"] >= 4
    assert len(result["sub_questions"]) > 0


def test_diagnostic_agent_analyze_question_unknown():
    from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent
    agent = DiagnosticChatAgent.__new__(DiagnosticChatAgent)
    result = agent._analyze_question("今天天气怎么样")
    assert result["is_diagnostic"] is False


def test_diagnostic_agent_decompose():
    from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent
    agent = DiagnosticChatAgent.__new__(DiagnosticChatAgent)
    parts = agent._decompose("问题1是什么？问题2如何处理？问题3怎么排查？")
    assert len(parts) == 3


def test_diagnostic_agent_decompose_numbered():
    from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent
    agent = DiagnosticChatAgent.__new__(DiagnosticChatAgent)
    parts = agent._decompose("请帮我：\n1. 检查USB\n2. 检查蓝牙\n3. 检查网络")
    assert len(parts) >= 2


def test_diagnostic_agent_decompose_single():
    from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent
    agent = DiagnosticChatAgent.__new__(DiagnosticChatAgent)
    parts = agent._decompose("USB超时怎么办")
    assert len(parts) == 1
    assert "USB超时怎么办" in parts[0]


def test_diagnostic_agent_exceed_max_length():
    from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent
    agent = DiagnosticChatAgent.__new__(DiagnosticChatAgent)
    long_text = "A" * 5000
    cleaned = agent._sanitize(long_text)
    assert len(cleaned) <= 4500  # 包含截断提示


# ═══════════════════════════════════════════════════════════
# ContextManager 边界测试
# ═══════════════════════════════════════════════════════════

def test_context_manager_should_compress():
    from app.services.chat.context_manager import ContextManager
    cm = ContextManager()
    few = [{"role": "user", "content": "hello"}] * 5
    assert cm.should_compress(few) is False
    many = [{"role": "user", "content": "hello"}] * 25
    assert cm.should_compress(many) is True


def test_context_manager_estimate_tokens():
    from app.services.chat.context_manager import ContextManager
    cm = ContextManager()
    english = [{"role": "user", "content": "Hello world"}]
    tokens_en = cm._estimate_tokens(english)
    assert tokens_en > 0
    chinese = [{"role": "user", "content": "你好世界"}]
    tokens_cn = cm._estimate_tokens(chinese)
    assert tokens_cn > 0
    # 中文 token 数应高于英文（因为中文字数多但英文单词数少）


def test_context_manager_compress():
    from app.services.chat.context_manager import ContextManager
    cm = ContextManager()
    messages = [{"role": "user", "content": f"message {i}"} for i in range(30)]
    compressed = cm._compress_messages(messages)
    assert len(compressed) < len(messages)
    # 应包含摘要信息
    assert any("摘要" in m.get("content", "") for m in compressed)


def test_context_manager_manage_no_compress():
    from app.services.chat.context_manager import ContextManager
    cm = ContextManager()
    messages = [{"role": "user", "content": "short"}] * 3
    result = cm.manage_context(messages)
    assert result == messages  # 短对话不压缩


def test_context_manager_generate_summary():
    from app.services.chat.context_manager import ContextManager
    cm = ContextManager()
    summary = cm._generate_summary([
        {"role": "user", "content": "USB timeout issue"},
        {"role": "assistant", "content": "Please check the USB controller"},
    ])
    assert "USB" in summary
    assert len(summary) > 0


# ═══════════════════════════════════════════════════════════
# TitleGenerator 边界测试
# ═══════════════════════════════════════════════════════════

def test_should_generate_title_new():
    from app.services.chat.title_generator import should_generate_title
    # should_generate_title takes (session_title, message_count: int)
    assert should_generate_title(None, 0) is False  # 0条消息不生成
    assert should_generate_title(None, 2) is True    # >=2条触发
    assert should_generate_title("新对话", 3) is True  # 默认标题仍生成


def test_should_generate_title_has_title():
    from app.services.chat.title_generator import should_generate_title
    assert should_generate_title("USB超时问题", 5) is False  # 已有有效标题不再生成


def test_should_generate_title_too_many_messages():
    from app.services.chat.title_generator import should_generate_title
    # 消息多但无有效标题时仍应生成
    assert should_generate_title(None, 10) is True


# ═══════════════════════════════════════════════════════════
# RAG Prompt Tests
# ═══════════════════════════════════════════════════════════

def test_rag_prompt_imports():
    from app.services.rag.rag_prompt import (
        RAG_STRICT_SYSTEM_PROMPT,
        RAG_NO_MATCH_RESPONSE,
        RAG_PARTIAL_MATCH_HINT,
    )
    assert len(RAG_STRICT_SYSTEM_PROMPT) > 100
    assert len(RAG_NO_MATCH_RESPONSE) > 10
    assert len(RAG_PARTIAL_MATCH_HINT) > 10
    assert "知识库" in RAG_STRICT_SYSTEM_PROMPT


# ═══════════════════════════════════════════════════════════
# FunctionCalling Agent 边界测试
# ═══════════════════════════════════════════════════════════

def test_function_calling_extract_tool_calls_json():
    from app.services.chat.function_calling_agent import FunctionCallingAgent
    agent = FunctionCallingAgent.__new__(FunctionCallingAgent)
    response = '```json\n{"tool_calls": [{"name": "search_knowledge", "arguments": {"query": "USB"}}]}\n```'
    calls = agent._extract_tool_calls(response)
    assert len(calls) == 1
    assert calls[0]["name"] == "search_knowledge"


def test_function_calling_extract_no_tool_calls():
    from app.services.chat.function_calling_agent import FunctionCallingAgent
    agent = FunctionCallingAgent.__new__(FunctionCallingAgent)
    response = "这是一个普通的回复，不需要调用工具。"
    calls = agent._extract_tool_calls(response)
    assert calls == []


def test_function_calling_extract_invalid_json():
    from app.services.chat.function_calling_agent import FunctionCallingAgent
    agent = FunctionCallingAgent.__new__(FunctionCallingAgent)
    response = '```json\n{invalid json content}\n```'
    calls = agent._extract_tool_calls(response)
    assert calls == []


def test_function_calling_max_iterations():
    from app.services.chat.function_calling_agent import MAX_TOOL_CALLS
    assert MAX_TOOL_CALLS > 0
    assert MAX_TOOL_CALLS <= 10


# ═══════════════════════════════════════════════════════════
# Knowledge Search 边界测试
# ═══════════════════════════════════════════════════════════

def test_knowledge_tokenize_query():
    from app.services.knowledge.knowledge_service import KnowledgeService
    tokens = KnowledgeService._tokenize_query("USB timeout 超时")
    assert len(tokens) > 0
    assert "USB" in tokens or "usb" in [t.lower() for t in tokens]


def test_knowledge_tokenize_chinese_only():
    from app.services.knowledge.knowledge_service import KnowledgeService
    tokens = KnowledgeService._tokenize_query("设备黑屏无法开机")
    assert len(tokens) > 0
    assert any(t in tokens for t in ["设备", "黑屏", "无法", "开机"])


def test_knowledge_tokenize_filters_stop_words():
    from app.services.knowledge.knowledge_service import KnowledgeService
    tokens = KnowledgeService._tokenize_query("我的设备出了问题")
    # "的" "了" 应被过滤
    assert "的" not in tokens
    assert "了" not in tokens


def test_knowledge_relevance_score():
    from app.services.knowledge.knowledge_service import KnowledgeService
    from app.models import KnowledgeDocument
    doc = KnowledgeDocument(title="USB Timeout", content="USB timeout handling guide")
    score = KnowledgeService._relevance_score(doc, "USB")
    assert 0 <= score <= 1


def test_knowledge_token_relevance():
    from app.services.knowledge.knowledge_service import KnowledgeService
    from app.models import KnowledgeDocument
    doc = KnowledgeDocument(title="USB Timeout", content="How to handle USB timeout")
    score = KnowledgeService._token_relevance(doc, ["usb", "timeout"])
    assert 0 <= score <= 1


def test_knowledge_extract_snippet():
    from app.services.knowledge.knowledge_service import KnowledgeService
    content = "This is a very long text with USB keyword somewhere in the middle of the document"
    snippet = KnowledgeService._extract_snippet(content, "USB")
    assert "USB" in snippet
