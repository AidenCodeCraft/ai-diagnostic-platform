"""Tests for prompt templates and structured LLM output parsing."""
from __future__ import annotations

import json

from app.services.prompts.diagnostic_prompt import DiagnosticPrompt
from app.services.providers.deepseek_provider import DeepSeekProvider


# ------------------------------------------------------------------
# DiagnosticPrompt
# ------------------------------------------------------------------


def test_prompt_build_includes_error_summary():
    events = [
        {"is_error": True, "classification": "timeout", "module": "usb"},
        {"is_error": True, "classification": "timeout", "module": "usb"},
        {"is_error": False, "classification": "normal", "module": "system"},
    ]
    prompt = DiagnosticPrompt.build("raw log", events)
    assert "ERROR SUMMARY" in prompt
    assert "timeout" in prompt
    assert "2 occurrences" in prompt


def test_prompt_build_no_errors():
    events = [
        {"is_error": False, "classification": "normal", "module": "system"},
    ]
    prompt = DiagnosticPrompt.build("raw log", events)
    assert "No error events detected" in prompt


def test_prompt_version():
    assert DiagnosticPrompt.VERSION == "1.0"


# ------------------------------------------------------------------
# DeepSeek response parsing
# ------------------------------------------------------------------


def test_deepseek_parse_direct_json():
    provider = DeepSeekProvider(api_key="test")
    raw = '{"summary": "USB timeout detected", "confidence": 0.9, "root_cause": "PHY error", "next_steps": ["check cable"]}'
    result = provider._parse_response(raw)
    assert result is not None
    assert result["summary"] == "USB timeout detected"
    assert result["confidence"] == 0.9


def test_deepseek_parse_markdown_fenced_json():
    provider = DeepSeekProvider(api_key="test")
    raw = '```json\n{"summary": "ok", "confidence": 0.8, "root_cause": "driver", "next_steps": ["step1"]}\n```'
    result = provider._parse_response(raw)
    assert result is not None
    assert result["confidence"] == 0.8


def test_deepseek_parse_invalid_returns_none():
    provider = DeepSeekProvider(api_key="test")
    result = provider._parse_response("just some text, no json here")
    assert result is None


def test_deepseek_parse_empty_returns_none():
    provider = DeepSeekProvider(api_key="test")
    result = provider._parse_response("")
    assert result is None


def test_deepseek_build_response_clamps_confidence():
    provider = DeepSeekProvider(api_key="test")
    parsed = {"summary": "x", "confidence": 2.5, "root_cause": "y", "next_steps": []}
    result = provider._build_response(parsed, [], 0)
    assert result["confidence"] == 1.0  # clamped to max


def test_deepseek_build_response_negative_confidence():
    provider = DeepSeekProvider(api_key="test")
    parsed = {"summary": "x", "confidence": -0.5, "root_cause": "y", "next_steps": []}
    result = provider._build_response(parsed, [], 0)
    assert result["confidence"] == 0.0  # clamped to min


def test_deepseek_health_check_with_key():
    provider = DeepSeekProvider(api_key="sk-test")
    assert provider.health_check() is True


def test_deepseek_health_check_without_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    provider = DeepSeekProvider(api_key="")
    assert provider.health_check() is False


def test_deepseek_fallback_returns_structured():
    events = [{"is_error": True, "module": "usb", "classification": "timeout"}]
    result = DeepSeekProvider._fallback_response(events, 1, "unavailable", 0.3)
    assert result["model"] == "deepseek"
    assert result["confidence"] == 0.3
    assert len(result["next_steps"]) > 0
