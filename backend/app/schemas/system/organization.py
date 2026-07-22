"""Schema definitions for organization management."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class OrganizationCreate(BaseModel):
    name: str = Field(..., max_length=100)


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    owner_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class OrganizationListResponse(BaseModel):
    items: List[OrganizationResponse]
    total: int
