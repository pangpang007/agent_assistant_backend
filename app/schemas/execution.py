import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ExecutionResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    version_number: int
    status: str
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    total_duration_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    total_cost: Optional[Decimal] = None
    started_at: datetime
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ExecutionNodeResponse(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    node_id: str
    node_type: str
    status: str
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    duration_ms: Optional[int] = None
    tokens_used: Optional[int] = None
    error_message: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LogResponse(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    level: str
    message: str
    node_id: Optional[str] = None
    timestamp: datetime

    model_config = {"from_attributes": True}
