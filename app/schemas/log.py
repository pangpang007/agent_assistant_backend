import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class LogListItem(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    workflow_name: str
    level: str
    message: str
    node_id: Optional[str] = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class LogListResponse(BaseModel):
    items: list[LogListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class LogDetailResponse(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: str
    level: str
    message: str
    node_id: Optional[str] = None
    timestamp: datetime
    metadata: dict[str, Any] = {}

    model_config = {"from_attributes": True}
