"""WebSocket 消息格式（Phase 5 实现，Phase 4 仅定义 Schema）。"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class WSNodeStatusMessage(BaseModel):
    type: str = "node_status"
    node_id: str
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    output: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    tokens_used: Optional[int] = None


class WSLogMessage(BaseModel):
    type: str = "log"
    level: str
    message: str
    node_id: Optional[str] = None
    timestamp: datetime


class WSExecutionCompleteMessage(BaseModel):
    type: str = "execution_complete"
    execution_id: str
    status: str
    total_duration_ms: int
    total_tokens: int
    output: Optional[dict] = None


class WSErrorMessage(BaseModel):
    type: str = "error"
    code: str
    message: str


class WSReviewActionMessage(BaseModel):
    type: str = "review_action"
    node_id: str
    action: str
    modified_data: Optional[dict] = None
    comment: Optional[str] = None
