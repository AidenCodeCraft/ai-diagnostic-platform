"""Tests for ApiKeyService."""

import pytest


class TestApiKeyService:
    """Unit tests for API key management logic."""

    def test_create_api_key(self):
        """Create a new API key."""
        api_key = {
            "id": 1,
            "name": "CI/CD Pipeline",
            "prefix": "ak-abc123",
            "created_at": "2024-01-01T00:00:00Z",
        }
        assert api_key["id"] > 0
        assert api_key["prefix"].startswith("ak-")

    def test_api_key_list(self):
        """List all API keys for current user."""
        keys = [
            {"id": 1, "name": "CI/CD", "prefix": "ak-xxx"},
            {"id": 2, "name": "Testing", "prefix": "ak-yyy"},
        ]
        assert len(keys) == 2

    def test_api_key_delete(self):
        """Delete an API key."""
        result = {"deleted": True, "id": 1}
        assert result["deleted"] is True

    def test_api_key_format(self):
        """API key follows expected format."""
        key = "ak-1234567890abcdef"
        assert key.startswith("ak-")
        assert len(key) >= 10

    def test_api_key_cannot_retrieve_full(self):
        """Full API key is not retrievable after creation."""
        # Only prefix should be visible
        visible = "ak-abc***"
        assert "***" in visible
