from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LogCreate(BaseModel):
    """Schema for creating a log record programmatically."""

    filename: str = Field(..., max_length=255)
    file_path: str = Field(..., max_length=500)
    size: Optional[int] = None
    project_id: Optional[int] = None
    upload_user_id: Optional[int] = None
    device: Optional[str] = Field(default=None, max_length=100)
    version: Optional[str] = Field(default=None, max_length=50)
    description: Optional[str] = Field(default=None, max_length=500)


class LogUpdate(BaseModel):
    """Schema for updating log metadata and status."""

    status: Optional[str] = Field(default=None, max_length=50)
    project_id: Optional[int] = None
    device: Optional[str] = Field(default=None, max_length=100)
    version: Optional[str] = Field(default=None, max_length=50)
    description: Optional[str] = Field(default=None, max_length=500)


class LogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_path: str
    size: Optional[int] = None
    status: str
    project_id: Optional[int] = None
    upload_user_id: Optional[int] = None
    device: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
