"""Schema definitions for bug case management."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class BugCaseCreate(BaseModel):
    title: str = Field(..., max_length=300)
    description: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=100)
    module: Optional[str] = Field(default=None, max_length=100)
    severity: str = Field(default="medium")
    root_cause: Optional[str] = None
    solution: Optional[str] = None
    confidence: Optional[float] = None
    log_id: Optional[int] = None


class BugCaseUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=100)
    module: Optional[str] = Field(default=None, max_length=100)
    severity: Optional[str] = Field(default=None)
    root_cause: Optional[str] = None
    solution: Optional[str] = None
    confidence: Optional[float] = None


class BugCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    module: Optional[str] = None
    severity: str
    root_cause: Optional[str] = None
    solution: Optional[str] = None
    confidence: Optional[float] = None
    log_id: Optional[int] = None
    analysis_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BugCaseListResponse(BaseModel):
    items: List[BugCaseResponse]
    total: int
    page: int = 1
    page_size: int = 20
