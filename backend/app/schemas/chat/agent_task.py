"""Schema definitions for agent task management."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentTaskCreate(BaseModel):
    log_id: int
    model: str = "mock"


class AgentTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: str
    log_id: int
    status: str
    state: str
    summary: Optional[str] = None
    error_message: Optional[str] = None
    tool_plan: Optional[Any] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
