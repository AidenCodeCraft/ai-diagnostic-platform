from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ClientLogEntrySchema(BaseModel):
    """Schema for a single frontend client log entry."""

    id: str = Field(..., max_length=64)
    timestamp: datetime
    level: int = Field(..., ge=0, le=5)
    category: str = Field(..., max_length=32)
    message: str = Field(..., max_length=10000)
    context: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class ClientLogBatchRequest(BaseModel):
    """Request schema for batch client log ingestion."""

    entries: List[ClientLogEntrySchema] = Field(..., min_length=1, max_length=200)
