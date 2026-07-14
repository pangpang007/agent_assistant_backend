"""WebSocket 消息格式（Phase 5）。"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


# ==================== 下行消息（服务端 → 客户端） ====================


class WSNodeStatusChange(BaseModel):
    """节点状态变更"""

    type: str = "node_status_change"
    node_id: str
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    output: Optional[Any] = None
    duration_ms: Optional[int] = None
    tokens_used: Optional[int] = None
    error: Optional[str] = None


class WSNodeStatusMessage(BaseModel):
    """节点状态（Phase 4 兼容）"""

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
    """实时日志"""

    type: str = "log"
    level: str
    message: str
    node_id: Optional[str] = None
    timestamp: str | datetime


class WSExecutionStatus(BaseModel):
    """执行状态变更"""

    type: str = "execution_status"
    status: str
    total_duration_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    total_nodes: Optional[int] = None
    output: Optional[dict] = None
    error: Optional[str] = None


class WSExecutionCompleteMessage(BaseModel):
    """执行完成（Phase 4 兼容）"""

    type: str = "execution_complete"
    execution_id: str
    status: str
    total_duration_ms: int
    total_tokens: int
    output: Optional[dict] = None


class WSReviewRequest(BaseModel):
    """审核请求"""

    type: str = "review_request"
    node_id: str
    input_data: Optional[dict] = None


class WSReviewResult(BaseModel):
    """审核结果"""

    type: str = "review_result"
    node_id: str
    action: str
    comment: Optional[str] = None
    modified_data: Optional[dict] = None


class WSExecutionPaused(BaseModel):
    """执行暂停（审核等待）"""

    type: str = "execution_paused"
    execution_id: str
    node_id: str
    reason: str = "review"


class WSErrorMessage(BaseModel):
    """错误消息"""

    type: str = "error"
    node_id: Optional[str] = None
    error_message: Optional[str] = None
    code: Optional[str] = None
    message: Optional[str] = None


class WSConnectedMessage(BaseModel):
    """连接成功消息"""

    type: str = "connected"
    execution_id: str
    message: str


# ==================== 上行消息（客户端 → 服务端） ====================


class WSPingMessage(BaseModel):
    """心跳"""

    type: str = "ping"


class WSReviewActionMessage(BaseModel):
    """审核操作（客户端上行，推荐走 HTTP API）"""

    type: str = "review_action"
    node_id: str
    action: str
    modified_data: Optional[dict] = None
    comment: Optional[str] = None
