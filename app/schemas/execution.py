import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, Field


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
    workflow_name: str
    version_number: int
    status: str
    total_duration_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    total_cost: Optional[float] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    node_count: int = 0
    success_node_count: int = 0
    failed_node_count: int = 0

    model_config = {"from_attributes": True}


class ExecutionListResponse(BaseModel):
    items: list[ExecutionListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class ExecutionNodeDetail(BaseModel):
    id: uuid.UUID
    execution_id: Optional[uuid.UUID] = None
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


class NodeStats(BaseModel):
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    pending: int = 0
    running: int = 0
    paused: int = 0


class ExecutionDetailResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: str
    version_number: int
    status: str
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    total_duration_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    total_cost: Optional[float] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    nodes: list[ExecutionNodeDetail] = []
    node_stats: NodeStats = Field(default_factory=NodeStats)
    success_rate: float = 0.0
    log_count: int = 0

    model_config = {"from_attributes": True}


class ExecutionStatsSummary(BaseModel):
    total_executions: int
    success_count: int
    failed_count: int
    success_rate: float
    avg_duration_ms: int
    total_tokens: int
    total_cost: float


class DailyTrendItem(BaseModel):
    date: str
    count: int
    success_count: int
    avg_duration_ms: int


class WorkflowStatsItem(BaseModel):
    workflow_id: str
    workflow_name: str
    execution_count: int
    success_count: int
    avg_duration_ms: int


class ExecutionStatsResponse(BaseModel):
    summary: ExecutionStatsSummary
    daily_trend: list[DailyTrendItem]
    by_workflow: list[WorkflowStatsItem]


# Legacy aliases for backward compatibility
ExecutionResponse = ExecutionDetailResponse
ExecutionNodeResponse = ExecutionNodeDetail


# ==================== 审核操作 ====================


class ReviewActionRequest(BaseModel):
    """审核节点操作请求"""

    action: str = Field(..., pattern="^(approve|reject|modify)$")
    node_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("node_id", "nodeId"),
        description="兼容 POST /executions/{id}/review；路径含 node_id 时可省略",
    )
    modified_data: Optional[dict[str, Any]] = Field(
        default=None,
        validation_alias=AliasChoices("modified_data", "modifiedOutput"),
    )
    comment: Optional[str] = Field(default=None, max_length=5000)


class ReviewActionResponse(BaseModel):
    execution_id: uuid.UUID
    node_id: str
    action: str
    message: str = "审核操作已处理"


ReviewRequest = ReviewActionRequest
ReviewResponse = ReviewActionResponse


# ==================== 取消执行 ====================


class CancelExecutionResponse(BaseModel):
    execution_id: uuid.UUID
    status: str = "cancelled"
    message: str = "执行已取消"


# ==================== 日志查询（按执行） ====================


class LogListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    execution_id: Optional[uuid.UUID] = None
    node_id: Optional[str] = None
    level: Optional[str] = Field(default=None, pattern="^(info|warn|error)$")


class ExecutionLogDetailResponse(BaseModel):
    """单次执行下的日志条目（不含 workflow_name）。"""

    id: uuid.UUID
    execution_id: uuid.UUID
    node_id: Optional[str] = None
    level: str
    message: str
    timestamp: datetime

    model_config = {"from_attributes": True}


class ExecutionLogListResponse(BaseModel):
    items: list[ExecutionLogDetailResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


# Keep Phase 5 names used by log_service / executions API
LogDetailResponse = ExecutionLogDetailResponse
LogListResponse = ExecutionLogListResponse
LogResponse = ExecutionLogDetailResponse
