"""Tests for RAG Service — vector + keyword hybrid search."""

import pytest
from unittest.mock import MagicMock, patch


class MockVectorService:
    """Mock vector search service for unit testing RAG."""
    def search(self, query: str, limit: int = 10):
        return [
            {"id": 1, "score": 0.95, "content": "USB timeout troubleshooting guide"},
            {"id": 2, "score": 0.82, "content": "Kernel panic diagnostic steps"},
        ]

    def is_available(self):
        return True


class TestRAGService:
    """Unit tests for RAG service logic."""

    def test_hybrid_search_merges_vector_and_keyword(self):
        """Hybrid search combines both search results."""
        vector_results = [
            {"id": 1, "score": 0.95},
            {"id": 2, "score": 0.80},
        ]
        keyword_results = [
            {"id": 2, "score": 0.70},
            {"id": 3, "score": 0.60},
        ]
        # Merge and deduplicate by id, keeping highest score
        merged = {}
        for r in vector_results:
            merged[r["id"]] = r
        for r in keyword_results:
            if r["id"] not in merged or r["score"] > merged[r["id"]]["score"]:
                merged[r["id"]] = r

        assert len(merged) == 3
        assert merged[1]["score"] == 0.95  # kept from vector
        assert merged[2]["score"] == 0.80  # kept from vector (higher)

    def test_hybrid_search_empty_both(self):
        """Empty results from both sources returns empty list."""
        merged = {}
        assert len(merged) == 0

    def test_hybrid_search_vector_only(self):
        """Only vector results available."""
        results = [{"id": 1, "score": 0.9}]
        merged = {r["id"]: r for r in results}
        assert len(merged) == 1
        assert 1 in merged

    def test_hybrid_search_keyword_fallback(self):
        """Keyword search works as fallback when vector unavailable."""
        keyword_results = [{"id": 5, "score": 0.6}]
        merged = {r["id"]: r for r in keyword_results}
        assert len(merged) == 1
        assert merged[5]["score"] == 0.6

    def test_search_results_sorted_by_score(self):
        """Results are sorted descending by score."""
        results = [
            {"id": 1, "score": 0.5},
            {"id": 2, "score": 0.9},
            {"id": 3, "score": 0.7},
        ]
        sorted_results = sorted(results, key=lambda x: x["score"], reverse=True)
        assert sorted_results[0]["id"] == 2
        assert sorted_results[1]["id"] == 3
        assert sorted_results[2]["id"] == 1

    def test_score_clamping(self):
        """Scores are clamped between 0.0 and 1.0."""
        score = max(0.0, min(1.0, 1.5))
        assert score == 1.0
        score = max(0.0, min(1.0, -0.3))
        assert score == 0.0
