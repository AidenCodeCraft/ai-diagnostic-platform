from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeProfileCreate(BaseModel):
    """知识条目「诊断剧本」的结构化字段。"""

    symptom: Optional[str] = None
    environment: Optional[str] = Field(default=None, max_length=300)
    log_keywords: Optional[List[str]] = None
    log_patterns: Optional[List[str]] = None
    negative_patterns: Optional[List[str]] = None
    expected: Optional[str] = None
    root_cause: Optional[str] = None
    solution: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: Optional[str] = None
    source: Optional[str] = None


class KnowledgeProfileResponse(BaseModel):
    id: int
    doc_id: int
    symptom: Optional[str] = None
    environment: Optional[str] = None
    log_keywords: List[str] = []
    log_patterns: List[str] = []
    negative_patterns: List[str] = []
    expected: Optional[str] = None
    root_cause: Optional[str] = None
    solution: Optional[str] = None
    confidence: float = 0.8
    status: str = "active"
    source: str = "manual"


class KnowledgeCreate(BaseModel):
    title: str = Field(..., max_length=200)
    content: str
    category: Optional[str] = Field(default=None, max_length=100)
    source: Optional[str] = Field(default=None, max_length=200)
    doc_type: str = Field(default="manual", max_length=50)
    project_id: Optional[int] = None
    parent_id: Optional[int] = None
    profile: Optional[KnowledgeProfileCreate] = None


class KnowledgeUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    content: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=100)
    source: Optional[str] = Field(default=None, max_length=200)
    doc_type: Optional[str] = Field(default=None, max_length=50)
    project_id: Optional[int] = None
    status: Optional[str] = Field(default=None, max_length=50)
    is_pinned: Optional[bool] = None
    profile: Optional[KnowledgeProfileCreate] = None


class KnowledgeImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_id: Optional[int] = None
    url: str
    caption: Optional[str] = None
    anchor: Optional[str] = None
    mime_type: str = "image/png"
    width: Optional[int] = None
    height: Optional[int] = None


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
    is_pinned: bool = False
    vector_id: Optional[str] = None
    quality_score: Optional[float] = None
    images: List[KnowledgeImageResponse] = []
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
