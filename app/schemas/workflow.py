import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ==================== 工作流 CRUD ====================

class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    nodes_data: Optional[list[dict[str, Any]]] = None
    edges_data: Optional[list[dict[str, Any]]] = None


class WorkflowUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    nodes_data: Optional[list[dict[str, Any]]] = None
    edges_data: Optional[list[dict[str, Any]]] = None


class WorkflowListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    keyword: Optional[str] = Field(default=None, max_length=100)
    sort_by: str = Field(default="updated_at", pattern="^(name|created_at|updated_at)$")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")


class WorkflowListItem(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    node_count: int = 0
    current_version: int
    is_published_api: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowListResponse(BaseModel):
    items: list[WorkflowListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class WorkflowDetailResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: Optional[str] = None
    nodes_data: Optional[list] = None
    edges_data: Optional[list] = None
    current_version: int
    is_published_api: bool
    published_api_key: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowDeleteResponse(BaseModel):
    message: str = "工作流已删除"
    workflow_id: uuid.UUID


# ==================== 版本管理 ====================

class WorkflowVersionResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    version_number: int
    tag: Optional[str] = None
    node_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowVersionDetailResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    version_number: int
    tag: Optional[str] = None
    nodes_data: Optional[list] = None
    edges_data: Optional[list] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class VersionRollbackResponse(BaseModel):
    message: str = "已回滚到版本 {version_number}"
    workflow_id: uuid.UUID
    version_number: int
    new_version_number: int  # 回滚后产生的新版本号


class VersionDiffResponse(BaseModel):
    v1: int
    v2: int
    added_nodes: list[dict]      # 新增的节点
    removed_nodes: list[dict]    # 删除的节点
    modified_nodes: list[dict]   # 修改的节点（含字段级 diff）
    added_edges: list[dict]      # 新增的边
    removed_edges: list[dict]    # 删除的边
    modified_edges: list[dict]   # 修改的边


# ==================== 工作流校验 ====================

class ValidationIssue(BaseModel):
    level: str            # "error" | "warning"
    code: str             # 问题代码，如 "ORPHAN_NODE"
    message: str          # 可读描述
    node_id: Optional[str] = None  # 关联的节点 ID（如果有）
    details: Optional[dict] = None # 附加信息


class ValidationResultResponse(BaseModel):
    is_valid: bool
    error_count: int
    warning_count: int
    issues: list[ValidationIssue]


# ==================== 单节点调试 ====================

class NodeTestRequest(BaseModel):
    node_id: str = Field(..., min_length=1)
    node_type: str = Field(..., min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)  # 节点的 data 配置
    input_variables: dict[str, Any] = Field(default_factory=dict)  # 模拟输入变量


class NodeTestResponse(BaseModel):
    output: Optional[Any] = None
    duration_ms: int
    tokens_used: Optional[int] = None
    error: Optional[str] = None


# ==================== 导入/导出 ====================

class WorkflowExportResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    version: str = "1.0"  # 导出格式版本
    exported_at: datetime
    nodes_data: list[dict[str, Any]]
    edges_data: list[dict[str, Any]]
    metadata: dict[str, Any] = {}  # 额外元数据（节点类型版本等）


class WorkflowImportRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    # 不传则使用导出数据中的 name
    description: Optional[str] = Field(default=None, max_length=5000)
    data: WorkflowExportResponse  # 导出的完整 JSON 结构
    # 如果同名工作流存在，前端应提前提示用户


class WorkflowImportResponse(BaseModel):
    id: uuid.UUID
    name: str
    message: str = "工作流导入成功"
