"""Vector search service — Milvus (production) / keyword (fallback).

In production this connects to a Milvus instance for semantic vector search.
In development, falls back to the existing keyword search in KnowledgeService.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class VectorService:
    """Vector search facade with Milvus-ready interface and keyword fallback."""

    def __init__(self) -> None:
        self._milvus_available = False

    def search(
        self,
        query: str,
        top_k: int = 5,
        collection: str = "knowledge",
    ) -> List[Dict[str, Any]]:
        """Semantic search. Falls back to empty list if Milvus unavailable."""
        # In production: connect to Milvus, embed query, search by vector
        # For now, returns empty — caller should fall back to keyword search
        return []

    def index_document(self, doc_id: int, content: str) -> Optional[str]:
        """Index a document's content as a vector. Returns vector_id or None."""
        # In production: chunk content, embed, insert into Milvus
        return None

    def delete_document(self, doc_id: int) -> None:
        """Remove document vectors from the index."""
        pass

    def health_check(self) -> bool:
        return self._milvus_available

    @property
    def available(self) -> bool:
        return self._milvus_available
