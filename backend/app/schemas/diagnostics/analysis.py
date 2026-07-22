from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnalysisCreate(BaseModel):
    """Schema for creating a new analysis task."""

    log_id: int
    model: Optional[str] = Field(default=None, max_length=100)


class AnalysisUpdate(BaseModel):
    """Schema for updating an analysis task."""

    status: Optional[str] = Field(default=None, max_length=50)
    summary: Optional[str] = None
    root_cause: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    next_steps: Optional[List[str]] = None
    model: Optional[str] = Field(default=None, max_length=100)
    error_message: Optional[str] = None


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    log_id: int
    status: str
    summary: Optional[str] = None
    root_cause: Optional[str] = None
    confidence: Optional[float] = None
    next_steps: Optional[Any] = None  # Accept raw DB value, validate below
    model: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("next_steps", mode="before")
    @classmethod
    def parse_next_steps(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [v]
        return v


class AnalysisListResponse(BaseModel):
    items: List[AnalysisResponse]
    total: int
    page: int = 1
    page_size: int = 20
