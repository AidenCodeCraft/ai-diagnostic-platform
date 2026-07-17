from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class LogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    log_id: int
    filename: str
    file_path: str
    status: str
    project_id: Optional[int] = None
    device: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime
