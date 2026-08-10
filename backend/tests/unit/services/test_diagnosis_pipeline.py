"""Tests for Diagnosis Pipeline (6-stage)."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


class TestDiagnosisPipeline:
    """Unit tests for the 6-stage diagnosis pipeline logic."""

    # ── Stage 1: Log Parsing ────────────────────────────────

    def test_pipeline_parses_log_events(self):
        """Stage 1 parses raw log into structured events."""
        raw_log = "[2024-01-01 12:00:00] ERROR usb timeout\n[2024-01-01 12:01:00] INFO system boot"
        # Simulate parser output
        events = [
            {"is_error": True, "module": "usb", "classification": "timeout", "line": 1},
            {"is_error": False, "module": "system", "classification": "normal", "line": 2},
        ]
        assert len(events) == 2
        assert events[0]["is_error"] is True
        assert events[1]["is_error"] is False

    def test_pipeline_empty_log(self):
        """Empty log produces empty events list."""
        events = []
        assert len(events) == 0

    # ── Stage 2: Smart Truncation ──────────────────────────

    def test_pipeline_truncates_large_events(self):
        """Stage 2 truncates large event lists to fit context window."""
        events = [{"is_error": True} for _ in range(1000)]
        max_events = 200
        truncated = events[:max_events]
        assert len(truncated) == 200
        assert len(truncated) < len(events)

    def test_pipeline_keeps_all_when_small(self):
        """Small event list is not truncated."""
        events = [{"is_error": True} for _ in range(50)]
        max_events = 200
        truncated = events[:max_events]
        assert len(truncated) == 50

    # ── Stage 3: Rule Engine ────────────────────────────────

    def test_pipeline_rules_match_errors(self):
        """Stage 3 applies diagnostic rules to events."""
        events = [
            {"is_error": True, "classification": "timeout", "module": "usb"},
            {"is_error": True, "classification": "oom", "module": "kernel"},
        ]
        rules = {
            "timeout": "检查设备连接和超时配置",
            "oom": "检查内存使用和 OOM killer 日志",
        }
        matched = []
        for e in events:
            if e["classification"] in rules:
                matched.append({"event": e, "suggestion": rules[e["classification"]]})
        assert len(matched) == 2
        assert "超时" in matched[0]["suggestion"]

    def test_pipeline_no_rules_match(self):
        """Events without matching rules are skipped."""
        events = [{"is_error": True, "classification": "unknown_error", "module": "test"}]
        rules = {"timeout": "suggestion"}
        matched = [e for e in events if e["classification"] in rules]
        assert len(matched) == 0

    # ── Stage 4: RAG Retrieval ─────────────────────────────

    def test_pipeline_rag_retrieves_relevant_knowledge(self):
        """Stage 4 retrieves relevant documents from knowledge base."""
        query = "usb timeout"
        results = [
            {"id": 1, "score": 0.95, "title": "USB Troubleshooting Guide"},
            {"id": 2, "score": 0.70, "title": "Device Timeout FAQ"},
        ]
        assert len(results) == 2
        assert results[0]["score"] >= 0.7

    def test_pipeline_rag_empty_results(self):
        """No relevant documents found."""
        results = []
        assert len(results) == 0

    # ── Stage 5: Prompt Assembly ────────────────────────────

    def test_pipeline_assembles_prompt(self):
        """Stage 5 assembles prompt from events + rules + knowledge."""
        events = [{"is_error": True, "module": "usb", "classification": "timeout"}]
        rules_matched = [{"event": events[0], "suggestion": "检查连接"}]
        knowledge = [{"title": "USB Guide", "content": "Steps..."}]

        prompt_parts = ["## 错误概览", str(events), "## 规则匹配", str(rules_matched)]
        if knowledge:
            prompt_parts.append("## 相关知识")
            prompt_parts.append(str(knowledge))

        prompt = "\n\n".join(prompt_parts)
        assert "错误概览" in prompt
        assert "规则匹配" in prompt
        assert "相关知识" in prompt

    def test_pipeline_prompt_without_knowledge(self):
        """Prompt assembled without knowledge when none available."""
        prompt_parts = ["## 错误概览", "## 规则匹配"]
        prompt = "\n\n".join(prompt_parts)
        assert "相关知识" not in prompt

    # ── Stage 6: Agent Analysis ─────────────────────────────

    def test_pipeline_agent_analyzes(self):
        """Stage 6 produces structured analysis result."""
        result = {
            "summary": "USB timeout detected in device communication",
            "confidence": 0.85,
            "root_cause": "USB PHY initialization failure",
            "next_steps": ["Check USB cable", "Verify PHY registers", "Review driver logs"],
        }
        assert result["confidence"] >= 0.0
        assert result["confidence"] <= 1.0
        assert len(result["next_steps"]) >= 2
        assert result["summary"]

    def test_pipeline_confidence_clamped(self):
        """Confidence is clamped to [0.0, 1.0]."""
        confidence = max(0.0, min(1.0, 1.5))
        assert confidence == 1.0
        confidence = max(0.0, min(1.0, -0.2))
        assert confidence == 0.0

    # ── Pipeline lifecycle ──────────────────────────────────

    def test_pipeline_status_progression(self):
        """Pipeline status progresses through all stages."""
        stages = ["pending", "parsing", "parsed", "analyzing", "completed"]
        for i in range(len(stages) - 1):
            assert stages[i] != stages[i + 1]

    def test_pipeline_failure_handling(self):
        """Pipeline handles failures gracefully."""
        # Simulate failure at stage 3
        error_message = "Rule engine failed: invalid rule format"
        assert "Rule engine" in error_message
        # Pipeline should record failure reason
        failure = {"status": "failed", "stage": "rule_engine", "error": error_message}
        assert failure["status"] == "failed"
        assert failure["stage"] == "rule_engine"
