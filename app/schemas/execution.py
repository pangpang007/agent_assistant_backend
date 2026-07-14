import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


# ==================== 启动执行 ====================


class WorkflowRunRequest(BaseModel):
    """启动工作流执行的请求"""

    input_data: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunResponse(BaseModel):
    """启动执行响应"""

    execution_id: uuid.UUID
    status: str = "running"
    message: str = "工作流已开始执行"


# ==================== 执行记录 ====================


class ExecutionListItem(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: Optional[str] = None
    version_number: int
    status: str
    total_duration_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    started_at: datetime
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ExecutionListResponse(BaseModel):
    items: list[ExecutionListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class ExecutionNodeDetail(BaseModel):
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


class ExecutionDetailResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: Optional[str] = None
    version_number: int
    status: str
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    total_duration_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    total_cost: Optional[Decimal] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    nodes: list[ExecutionNodeDetail] = []

    model_config = {"from_attributes": True}


# Legacy aliases for backward compatibility
ExecutionResponse = ExecutionDetailResponse
ExecutionNodeResponse = ExecutionNodeDetail


# ==================== 审核操作 ====================


class ReviewActionRequest(BaseModel):
    """审核节点操作请求"""

    action: str = Field(..., pattern="^(approve|reject|modify)$")
    modified_data: Optional[dict[str, Any]] = None
    comment: Optional[str] = Field(default=None, max_length=5000)


class ReviewActionResponse(BaseModel):
    execution_id: uuid.UUID
    node_id: str
    action: str
    message: str = "审核操作已处理"


# Aliases per deliverable naming
ReviewRequest = ReviewActionRequest
ReviewResponse = ReviewActionResponse


# ==================== 取消执行 ====================


class CancelExecutionResponse(BaseModel):
    execution_id: uuid.UUID
    status: str = "cancelled"
    message: str = "执行已取消"


# ==================== 日志查询 ====================


class LogListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    execution_id: Optional[uuid.UUID] = None
    node_id: Optional[str] = None
    level: Optional[str] = Field(default=None, pattern="^(info|warn|error)$")


class LogDetailResponse(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    node_id: Optional[str] = None
    level: str
    message: str
    timestamp: datetime

    model_config = {"from_attributes": True}


class LogListResponse(BaseModel):
    items: list[LogDetailResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


# Legacy alias
LogResponse = LogDetailResponse
