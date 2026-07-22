"""Schema definitions for chat session and message management."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ChatSessionCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    model: Optional[str] = Field(default=None, max_length=50)


class ChatSessionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: Optional[str] = None
    user_id: Optional[int] = None
    model: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChatSessionListResponse(BaseModel):
    items: List[ChatSessionResponse]
    total: int


class ChatMessageCreate(BaseModel):
    role: str = Field(..., max_length=20)  # user / assistant
    content: str


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    role: str
    content: str
    created_at: Optional[datetime] = None
