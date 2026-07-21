from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeCreate(BaseModel):
    title: str = Field(..., max_length=200)
    content: str
    category: Optional[str] = Field(default=None, max_length=100)
    source: Optional[str] = Field(default=None, max_length=200)
    doc_type: str = Field(default="manual", max_length=50)
    project_id: Optional[int] = None
    parent_id: Optional[int] = None


class KnowledgeUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    content: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=100)
    source: Optional[str] = Field(default=None, max_length=200)
    doc_type: Optional[str] = Field(default=None, max_length=50)
    project_id: Optional[int] = None
    status: Optional[str] = Field(default=None, max_length=50)


class KnowledgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: Optional[str] = None
    content: str
    source: Optional[str] = None
    doc_type: str
    project_id: Optional[int] = None
    status: str
    vector_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class KnowledgeSearchResult(BaseModel):
    id: int
    title: str
    category: Optional[str] = None
    doc_type: str
    relevance_score: float = 0.0
    snippet: str = ""


class KnowledgeListResponse(BaseModel):
    items: List[KnowledgeResponse]
    total: int
    page: int = 1
    page_size: int = 20


class KnowledgeTreeNode(BaseModel):
    """Recursive tree node for folder/document hierarchy."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    doc_type: str
    category: Optional[str] = None
    updated_at: Optional[datetime] = None
    children: List["KnowledgeTreeNode"] = []


class KnowledgeTreeResponse(BaseModel):
    tree: List[KnowledgeTreeNode]
