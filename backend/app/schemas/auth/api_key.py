"""Schema definitions for API key management."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Optional[str] = None
    prefix: str
    is_active: bool
    last_used_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ApiKeyCreatedResponse(BaseModel):
    """Response after creating a new key — includes raw key (only shown once)."""
    id: int
    name: Optional[str] = None
    raw_key: str
    prefix: str
    message: str = "请保存此 API Key，关闭后将无法再次查看"


class ApiKeyListResponse(BaseModel):
    items: List[ApiKeyResponse]
    total: int
