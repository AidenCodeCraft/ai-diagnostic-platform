from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., max_length=100)
    chip: Optional[str] = Field(default=None, max_length=100)
    firmware: Optional[str] = Field(default=None, max_length=100)
    device_type: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    chip: Optional[str] = Field(default=None, max_length=100)
    firmware: Optional[str] = Field(default=None, max_length=100)
    device_type: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    chip: Optional[str] = None
    firmware: Optional[str] = None
    device_type: Optional[str] = None
    description: Optional[str] = None
    owner_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectListResponse(BaseModel):
    items: List[ProjectResponse]
    total: int
    page: int = 1
    page_size: int = 20
