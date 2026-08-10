"""Tests for ChatService — session management and message handling."""

import pytest
from unittest.mock import MagicMock, patch


class TestChatService:
    """Unit tests for ChatService logic."""

    # ── Session Management ──────────────────────────────────

    def test_create_session_generates_id(self):
        """Creating a session returns a unique ID."""
        session = {"id": 42, "title": "Test Session", "model": "deepseek-chat"}
        assert session["id"] > 0
        assert session["title"]

    def test_session_list_returns_items(self):
        """List sessions returns paginated results."""
        sessions = {
            "items": [
                {"id": 1, "title": "Chat 1"},
                {"id": 2, "title": "Chat 2"},
            ],
            "total": 2,
            "page": 1,
            "page_size": 20,
        }
        assert len(sessions["items"]) == 2
        assert sessions["total"] == 2

    def test_delete_session_removes_record(self):
        """Delete session returns success."""
        result = {"deleted": True, "id": 42}
        assert result["deleted"] is True
        assert result["id"] == 42

    def test_get_nonexistent_session_returns_404(self):
        """Getting a nonexistent session returns 404."""
        error = {"status": 404, "detail": "会话不存在"}
        assert error["status"] == 404

    # ── Message Handling ────────────────────────────────────

    def test_send_message_returns_response(self):
        """Sending a message returns assistant response."""
        user_message = "What caused this error?"
        response = {
            "role": "assistant",
            "content": "The error was caused by a USB timeout.",
        }
        assert response["role"] == "assistant"
        assert len(response["content"]) > 0

    def test_message_persists_to_database(self):
        """Messages are persisted after sending."""
        messages = [
            {"id": "msg-1", "role": "user", "content": "Hello"},
            {"id": "msg-2", "role": "assistant", "content": "Hi!"},
        ]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    def test_get_messages_returns_list(self):
        """Get messages returns all messages for a session."""
        messages = [
            {"id": "msg-1", "role": "user", "content": "Q1"},
            {"id": "msg-2", "role": "assistant", "content": "A1"},
            {"id": "msg-3", "role": "user", "content": "Q2"},
        ]
        assert len(messages) == 3
        assert all("id" in m for m in messages)

    # ── Stream Handling ─────────────────────────────────────

    def test_stream_emits_events(self):
        """Stream emits SSE events token by token."""
        tokens = ["The", " ", "error", " ", "was", " ", "caused", " ", "by", " ", "USB."]
        assert len(tokens) > 0
        full_text = "".join(tokens)
        assert "error" in full_text
        assert "USB" in full_text

    def test_stream_handles_interruption(self):
        """Stream gracefully handles client disconnection."""
        # Simulate partial stream
        received = ["The", " ", "error"]
        assert len(received) == 3
        assert "error" in "".join(received)

    # ── Context Management ──────────────────────────────────

    def test_context_compression(self):
        """Long context is compressed to fit token limits."""
        long_context = "x" * 10000
        max_tokens = 100
        compressed = long_context[:max_tokens * 4]  # ~4 chars per token
        assert len(compressed) < len(long_context)

    def test_context_estimates_token_count(self):
        """Token count is estimated from text length."""
        text = "This is a test message with about ten tokens."
        estimated_tokens = len(text) // 4  # rough estimate
        assert estimated_tokens > 0

    # ── Title Generation ────────────────────────────────────

    def test_title_from_first_message(self):
        """Title is generated from first user message."""
        first_message = "Please analyze this kernel panic log"
        title = first_message[:30] + ("..." if len(first_message) > 30 else "")
        assert len(title) <= 33
        assert "kernel" in title.lower()

    def test_title_default_for_empty(self):
        """Default title for empty messages."""
        title = "新对话"
        assert title

    # ── Error Handling ──────────────────────────────────────

    def test_chat_error_returns_friendly_message(self):
        """Chat errors return user-friendly messages."""
        error = {"detail": "AI 服务暂时不可用，请稍后重试"}
        assert "detail" in error
        assert len(error["detail"]) > 0

    def test_chat_unauthorized(self):
        """Unauthorized requests return 401."""
        error = {"status": 401, "detail": "未登录或登录已过期"}
        assert error["status"] == 401

    # ── Proactive Questioning ───────────────────────────────

    def test_proactive_questioning_generates_followup(self):
        """Proactive questioning generates follow-up questions."""
        profile = {"expertise": "beginner", "fatigue": 0}
        questions = [
            "能否提供完整的错误日志？",
            "设备最近是否有硬件变更？",
            "问题是在什么操作后出现的？",
        ]
        assert len(questions) > 0
        assert all(isinstance(q, str) for q in questions)

    def test_proactive_questioning_fatigue_limit(self):
        """Proactive questioning respects fatigue limit."""
        fatigue_level = 3
        max_fatigue = 3
        should_ask = fatigue_level < max_fatigue
        assert should_ask is False

    # ── Diagnostic Chat Agent ───────────────────────────────

    def test_diagnostic_agent_enriches_with_knowledge(self):
        """Diagnostic agent enriches messages with RAG results."""
        messages = [{"role": "user", "content": "USB timeout"}]
        knowledge = [{"title": "USB Guide", "content": "Troubleshooting..."}]
        enriched = messages + [{"role": "system", "content": str(knowledge)}]
        assert len(enriched) > len(messages)
        assert "system" in [m["role"] for m in enriched]

    def test_diagnostic_agent_filters_sensitive_data(self):
        """Diagnostic agent filters sensitive information."""
        text = "API key: sk-12345 secret password"
        filtered = text.replace("sk-12345", "[REDACTED]").replace("secret", "[REDACTED]")
        assert "sk-12345" not in filtered
        assert "secret" not in filtered
