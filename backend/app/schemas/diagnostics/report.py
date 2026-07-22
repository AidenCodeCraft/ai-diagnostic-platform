from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    log_id: Optional[int] = None
    analysis_id: Optional[int] = None
    title: Optional[str] = None
    format: str = "json"
    content: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ReportDetail(BaseModel):
    id: int
    log_id: Optional[int] = None
    analysis_id: Optional[int] = None
    title: Optional[str] = None
    format: str = "json"
    summary: str = ""
    root_cause: str = ""
    confidence: Optional[float] = None
    next_steps: List[str] = Field(default_factory=list)
    model: str = "mock"
    created_at: Optional[datetime] = None


class ReportListResponse(BaseModel):
    items: List[ReportDetail]
    total: int
    page: int = 1
    page_size: int = 20
