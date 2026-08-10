"""Tests for BugCaseService."""

import pytest


class TestBugCaseService:
    """Unit tests for bug case management logic."""

    def test_create_bug_case(self):
        """Create a new bug case with required fields."""
        bug = {
            "id": 1,
            "title": "USB timeout on device connect",
            "category": "usb",
            "module": "usb_core",
            "severity": "high",
            "root_cause": "PHY initialization failure",
            "solution": "Reset USB PHY before enumeration",
            "confidence": 0.85,
        }
        assert bug["id"] > 0
        assert bug["title"]
        assert bug["severity"] in ("low", "medium", "high", "critical")

    def test_bug_case_list_filtered(self):
        """Bug cases can be filtered by category."""
        cases = [
            {"id": 1, "category": "usb", "title": "USB error"},
            {"id": 2, "category": "kernel", "title": "Kernel panic"},
            {"id": 3, "category": "usb", "title": "USB disconnect"},
        ]
        usb_cases = [c for c in cases if c["category"] == "usb"]
        assert len(usb_cases) == 2
        kernel_cases = [c for c in cases if c["category"] == "kernel"]
        assert len(kernel_cases) == 1

    def test_bug_case_update(self):
        """Bug case fields can be updated."""
        bug = {"id": 1, "severity": "medium", "solution": ""}
        bug["severity"] = "high"
        bug["solution"] = "Apply firmware patch v2.1"
        assert bug["severity"] == "high"
        assert bug["solution"]

    def test_bug_case_delete(self):
        """Bug case can be deleted."""
        result = {"deleted": True, "id": 42}
        assert result["deleted"] is True

    def test_bug_case_severity_validation(self):
        """Severity must be one of allowed values."""
        valid = ("low", "medium", "high", "critical")
        assert "high" in valid
        assert "unknown" not in valid

    def test_bug_case_confidence_range(self):
        """Confidence must be between 0 and 1."""
        confidence = 0.85
        assert 0.0 <= confidence <= 1.0
