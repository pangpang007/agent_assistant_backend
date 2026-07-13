---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 4263223131904378_0/project_7661866342080954651-files/Phase4/phase4_backend.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 4263223131904378#1783942923494
    ReservedCode2: ""
---
# 汤圆的代码助手 - Phase 4 后端开发文档：工作流编辑器后端

> **目标读者**：Cursor / AI Coding Agent  
> **版本**：Phase 4 v1.0  
> **项目代号**：`tangyuan-backend`  
> **前置条件**：Phase 0（脚手架 + 全部数据库模型）+ Phase 1（用户系统）+ Phase 2（Agent + 工具 + 模型管理）+ Phase 3（知识库管理）已完成

---

## 1. 目标

在 Phase 0-3 基础上实现工作流编辑器的完整后端能力：

- **工作流 CRUD**：列表、创建、详情、更新（保存）、删除
- **版本管理**：每次保存自动创建版本、版本列表/详情、回滚、版本对比
- **工作流校验引擎**：连通性检查、必填项检查、DAG 环检测、变量引用校验
- **单节点调试**：按节点类型执行对应逻辑（Agent/知识检索/代码执行/HTTP/模板/条件分支等）
- **导入/导出**：JSON 格式完整导出与导入
- **WebSocket 接口定义**（Phase 5 实现，Phase 4 先定义 Schema）

Phase 4 完成后，用户应能：创建/编辑工作流 → 保存自动产生版本 → 校验工作流合法性 → 单节点调试 → 导入/导出工作流。

---

## 2. 数据库变更

### 2.1 Workflow 模型调整 `app/models/workflow.py`

Phase 0 定义的 Workflow 模型使用 `nodes_json` / `edges_json` 存储画布数据。Phase 4 将其重命名为语义更清晰的 `nodes_data` / `edges_data`，并完善字段。

```python
# app/models/workflow.py — Phase 4 完整模型

import uuid
from typing import Optional
from datetime import datetime

from sqlalchemy import String, Integer, Boolean, Text, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Index

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class Workflow(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "workflows"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Phase 4: JSONB 字段重命名，存储完整的画布节点/边数据
    nodes_data: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    edges_data: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)

    current_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    # API 发布相关（Phase 5+ 使用）
    is_published_api: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    published_api_key: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, unique=True
    )

    # Relationships
    user = relationship("User", back_populates="workflows")
    versions = relationship(
        "WorkflowVersion",
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowVersion.version_number.desc()",
    )
    executions = relationship("Execution", back_populates="workflow", cascade="all, delete-orphan")


class WorkflowVersion(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "workflow_versions"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tag: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    nodes_data: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    edges_data: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # Relationships
    workflow = relationship("Workflow", back_populates="versions")

    # Constraints
    __table_args__ = (
        # 同一工作流下版本号唯一
        Index("ix_workflow_versions_wf_ver", "workflow_id", "version_number", unique=True),
    )
```

**字段变更说明**：

| 变更项 | Phase 0 | Phase 4 |
|--------|---------|---------|
| 节点数据字段 | `nodes_json` | 重命名为 `nodes_data` |
| 边数据字段 | `edges_json` | 重命名为 `edges_data` |
| 默认值 | `nullable=True`，无默认 | `nullable=True, default=list` |
| 版本表唯一约束 | 无 | 新增 `(workflow_id, version_number)` 联合唯一索引 |
| 版本排序 | 无 | relationship 默认按 version_number DESC |

**Alembic 迁移**：

```bash
alembic revision --autogenerate -m "phase4_workflow_nodes_edges_rename"
alembic upgrade head
```

迁移内容摘要：
1. `workflows` 表：`nodes_json` 重命名为 `nodes_data`，`edges_json` 重命名为 `edges_data`
2. `workflow_versions` 表：同步重命名字段，新增联合唯一索引

---

### 2.2 JSONB 数据结构设计

#### 2.2.1 `nodes_data` JSON Schema

`nodes_data` 是一个节点数组，每个节点遵循 React Flow 的节点数据格式：

```jsonc
// nodes_data 整体结构
[
  {
    "id": "node_start_1",          // 节点唯一 ID（前端生成）
    "type": "startNode",           // 节点类型标识（对应 React Flow 注册的组件名）
    "position": {                  // 画布上的位置（前端用，后端透传存储）
      "x": 250,
      "y": 50
    },
    "data": {                      // 节点的业务配置数据
      "label": "开始",             // 显示名称
      "inputs": [                  // 节点定义的输入变量
        {
          "name": "user_query",
          "type": "string",        // string | number | boolean | object | array
          "description": "用户输入的问题",
          "required": true,
          "default_value": null
        }
      ],
      "outputs": [                 // 节点定义的输出变量
        {
          "name": "user_query",
          "type": "string",
          "description": "透传用户输入"
        }
      ],
      // ---- 以下为各类型节点特有的配置 ----
      // startNode 无额外配置

      // agentNode 额外字段:
      // "agent_id": "uuid",           // 关联的 Agent ID
      // "input_mapping": {            // 输入变量映射
      //   "agent_input_key": "${node_start_1.user_query}"
      // },
      // "output_key": "result",       // 输出变量名

      // knowledgeRetrievalNode:
      // "knowledge_base_id": "uuid",
      // "query_template": "${node_start_1.user_query}",
      // "top_k": 5,
      // "score_threshold": 0.7,
      // "output_key": "retrieved_docs"

      // codeNode:
      // "language": "python",         // python | javascript
      // "code": "def main(input):\n  return {'result': input.upper()}",
      // "input_mapping": { "input": "${node_start_1.user_query}" },
      // "output_key": "code_result"

      // httpNode:
      // "method": "POST",
      // "url": "https://api.example.com/data",
      // "headers": { "Content-Type": "application/json" },
      // "body_template": "{ \"query\": \"${node_start_1.user_query}\" }",
      // "auth": { "type": "bearer", "token": "${env.API_TOKEN}" },
      // "timeout": 30,
      // "output_key": "http_response"

      // templateNode:
      // "template": "用户问题: {{ query }}\n检索结果: {{ docs }}",
      // "input_mapping": {
      //   "query": "${node_start_1.user_query}",
      //   "docs": "${node_kb_1.retrieved_docs}"
      // },
      // "output_key": "rendered_text"

      // conditionNode:
      // "conditions": [
      //   {
      //     "id": "cond_1",
      //     "variable": "${node_agent_1.result}",
      //     "operator": "contains",    // equals | not_equals | contains | not_contains | starts_with | ends_with | regex | is_empty | is_not_empty | gt | gte | lt | lte
      //     "value": "success"
      //   }
      // ],
      // "branches": [                  // 分支定义，与 conditions 一一对应
      //   { "id": "branch_true", "label": "条件成立", "condition_id": "cond_1" },
      //   { "id": "branch_false", "label": "默认分支", "condition_id": null }
      // ]

      // loopNode:
      // "loop_variable": "${node_xxx.array_output}",
      // "item_name": "current_item",
      // "index_name": "current_index"

      // parallelNode:
      // "branches": [
      //   { "id": "parallel_branch_1", "label": "分支1" },
      //   { "id": "parallel_branch_2", "label": "分支2" }
      // ],
      // "wait_mode": "all",           // all（等全部完成）| any（任一完成）

      // classifyNode（问题分类）:
      // "agent_id": "uuid",
      // "input_mapping": { "text": "${node_start_1.user_query}" },
      // "categories": [
      //   { "id": "cat_1", "label": "技术问题", "keywords": ["bug", "error"] },
      //   { "id": "cat_2", "label": "商务咨询", "keywords": ["价格", "合作"] },
      //   { "id": "cat_default", "label": "其他", "is_default": true }
      // ]

      // extractNode（参数提取）:
      // "agent_id": "uuid",
      // "input_mapping": { "text": "${node_start_1.user_query}" },
      // "extraction_schema": [
      //   { "name": "name", "type": "string", "description": "用户姓名" },
      //   { "name": "email", "type": "string", "description": "邮箱地址" }
      // ],
      // "output_key": "extracted_params"

      // reviewNode（审核节点）:
      // "reviewer_ids": ["uuid1"],
      // "timeout_seconds": 3600,
      // "on_timeout": "reject",       // approve | reject

      // testNode（测试节点）:
      // "assertions": [
      //   {
      //     "variable": "${node_agent_1.result}",
      //     "operator": "is_not_empty",
      //     "expected": null
      //   }
      // ],
      // "on_failure": "continue",     // continue | abort | retry
      // "retry_count": 3

      // delayNode（延时节点）:
      // "delay_seconds": 5

      // variableAggregateNode（变量聚合）:
      // "aggregations": [
      //   { "name": "combined", "sources": ["${node_p1.output}", "${node_p2.output}"], "mode": "array" }
      // ],
      // "output_key": "aggregated"

      // endNode（结束节点）:
      // "output_mapping": {
      //   "final_answer": "${node_agent_1.result}",
      //   "references": "${node_kb_1.retrieved_docs}"
      // }
    },
    "selected": false,               // 前端选中状态（后端透传）
    "dragging": false                // 前端拖拽状态（后端透传）
  }
]
```

#### 2.2.2 `edges_data` JSON Schema

`edges_data` 是一个边数组，遵循 React Flow 的边数据格式：

```jsonc
// edges_data 整体结构
[
  {
    "id": "edge_1",
    "source": "node_start_1",        // 源节点 ID
    "target": "node_agent_1",        // 目标节点 ID
    "sourceHandle": "output_1",      // 源节点的输出端口（条件分支节点有多个出口）
    "targetHandle": "input_1",       // 目标节点的输入端口
    "type": "default",               // 边的类型（default | smoothstep | step）
    "animated": true,                // 是否动画（运行时）
    "label": "",                     // 边上的标签（可选）
    "data": {                        // 自定义数据（可选）
      "condition_branch_id": null    // 条件分支节点出口关联的 branch_id
    }
  }
]
```

#### 2.2.3 节点类型常量定义

```python
# app/models/enums.py — Phase 4 新增节点类型枚举

class NodeType(str, enum.Enum):
    """工作流节点类型"""
    start = "startNode"
    end = "endNode"
    agent = "agentNode"
    knowledge_retrieval = "knowledgeRetrievalNode"
    code = "codeNode"
    http = "httpNode"
    template = "templateNode"
    condition = "conditionNode"
    parallel = "parallelNode"
    loop = "loopNode"
    classify = "classifyNode"
    extract = "extractNode"
    review = "reviewNode"
    test = "testNode"
    delay = "delayNode"
    variable_aggregate = "variableAggregateNode"
```

---

### 2.3 Pydantic Schema 定义 `app/schemas/workflow.py`

```python
# app/schemas/workflow.py — Phase 4 完整定义

import uuid
from datetime import datetime
from typing import Optional, Any
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
```

---

## 3. API 完整规格

### 3.0 通用约定

#### 成功响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

#### 认证方式

所有接口需要：`Authorization: Bearer <access_token>`

#### 权限模型

- 用户只能操作自己创建的工作流（`workflow.user_id == current_user.id`）
- 403 `FORBIDDEN`：尝试操作他人工作流时返回

---

### 3.1 工作流 CRUD

#### 3.1.1 获取工作流列表

**`GET /api/workflows`**

**描述**：获取当前用户的工作流列表，支持搜索、排序和分页。

**查询参数**：

```
page: int (default=1)
page_size: int (default=20, max=100)
keyword: string (可选, 模糊匹配 name 和 description)
sort_by: string (default="updated_at", 可选: "name" | "created_at" | "updated_at")
sort_order: string (default="desc", 可选: "asc" | "desc")
```

**业务逻辑**（`WorkflowService.list_workflows`）：

1. 获取当前用户
2. 构建查询：`WHERE user_id = :current_user_id`
3. 如有 `keyword`：`AND (name ILIKE '%keyword%' OR description ILIKE '%keyword%')`
4. 动态排序字段 + 排序方向
5. 分页查询，返回总数和分页数据
6. 对每条记录，计算 `node_count = len(workflow.nodes_data) if nodes_data else 0`

**响应体**：`WorkflowListResponse`

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 401 | `UNAUTHORIZED` | 未登录 |

---

#### 3.1.2 创建工作流

**`POST /api/workflows`**

**描述**：创建一个新的工作流，自动创建初始版本 v1。

**请求体**：`WorkflowCreate`

**业务逻辑**（`WorkflowService.create_workflow`）：

1. 获取当前用户
2. 创建工作流记录：`user_id = current_user.id`
3. 如果未提供 `nodes_data`，初始化为空列表 `[]`
4. 如果未提供 `edges_data`，初始化为空列表 `[]`
5. `current_version = 1`
6. 保存工作流
7. **自动创建初始版本**：调用 `VersionService.create_version()`
   - `version_number = 1`
   - `nodes_data` / `edges_data` 与工作流一致
8. 返回新工作流的完整详情

**响应体**：`WorkflowDetailResponse`

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 401 | `UNAUTHORIZED` | 未登录 |
| 422 | `VALIDATION_ERROR` | 参数校验失败 |

---

#### 3.1.3 获取工作流详情

**`GET /api/workflows/:id`**

**描述**：获取指定工作流的完整详情，包含当前画布数据。

**业务逻辑**（`WorkflowService.get_workflow`）：

1. 获取当前用户
2. 根据 `id` 查询工作流
3. 不存在 → 404 `WORKFLOW_NOT_FOUND`
4. 权限检查：`workflow.user_id != current_user.id` → 403 `FORBIDDEN`
5. 返回完整详情（含 nodes_data、edges_data）

**响应体**：`WorkflowDetailResponse`

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `WORKFLOW_NOT_FOUND` | 工作流不存在 |
| 403 | `FORBIDDEN` | 无权查看 |

---

#### 3.1.4 更新工作流（保存）

**`PUT /api/workflows/:id`**

**描述**：更新工作流配置和画布数据。**每次保存自动创建新版本**。

**请求体**：`WorkflowUpdate`（所有字段可选，只更新传入的字段）

**业务逻辑**（`WorkflowService.update_workflow`）：

1. 获取当前用户
2. 查询工作流 + 权限检查
3. 更新非 None 字段
4. 如果 `nodes_data` 或 `edges_data` 有变更：
   - 更新 `workflow.current_version += 1`
   - 调用 `VersionService.create_version()` 创建新版本
5. 返回更新后的工作流详情

**响应体**：`WorkflowDetailResponse`

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `WORKFLOW_NOT_FOUND` | 工作流不存在 |
| 403 | `FORBIDDEN` | 无权修改 |

---

#### 3.1.5 删除工作流

**`DELETE /api/workflows/:id`**

**描述**：删除工作流及其所有版本和执行记录。

**业务逻辑**（`WorkflowService.delete_workflow`）：

1. 获取当前用户
2. 查询工作流 + 权限检查
3. 删除工作流（cascade 自动删除关联的版本和执行记录）
4. 返回删除确认

**响应体**：`WorkflowDeleteResponse`

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `WORKFLOW_NOT_FOUND` | 工作流不存在 |
| 403 | `FORBIDDEN` | 无权删除 |

---

### 3.2 版本管理

#### 3.2.1 获取版本列表

**`GET /api/workflows/:id/versions`**

**描述**：获取工作流的版本历史列表，按版本号倒序排列。

**查询参数**：

```
page: int (default=1)
page_size: int (default=20, max=100)
```

**业务逻辑**（`VersionService.list_versions`）：

1. 查询工作流 + 权限检查
2. 按 `version_number DESC` 排序，分页查询
3. 对每个版本，计算 `node_count`

**响应体**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "uuid",
        "workflow_id": "uuid",
        "version_number": 5,
        "tag": "稳定版",
        "node_count": 12,
        "created_at": "2026-07-15T10:30:00Z"
      }
    ],
    "total": 5,
    "page": 1,
    "page_size": 20,
    "has_next": false
  }
}
```

---

#### 3.2.2 获取版本详情

**`GET /api/workflows/:id/versions/:ver`**

**描述**：获取指定版本的完整数据（含画布数据）。

**业务逻辑**（`VersionService.get_version`）：

1. 查询工作流 + 权限检查
2. 查询 `workflow_id = :id AND version_number = :ver` 的版本记录
3. 不存在 → 404 `VERSION_NOT_FOUND`
4. 返回完整版本数据

**响应体**：`WorkflowVersionDetailResponse`

---

#### 3.2.3 回滚到指定版本

**`POST /api/workflows/:id/versions/:ver/rollback`**

**描述**：回滚到指定版本。**回滚本身也会创建一个新版本**。

**业务逻辑**（`VersionService.rollback_to_version`）：

1. 查询工作流 + 权限检查
2. 查询目标版本（`version_number = :ver`）
3. 目标版本不存在 → 404 `VERSION_NOT_FOUND`
4. 将目标版本的 `nodes_data` / `edges_data` 复制到工作流
5. `workflow.current_version += 1`
6. 创建新版本，`tag = f"回滚自 v{ver}"`
7. 返回回滚信息（含新版本号）

**响应体**：`VersionRollbackResponse`

**示例**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "已回滚到版本 3",
    "workflow_id": "uuid",
    "version_number": 3,
    "new_version_number": 6
  }
}
```

---

#### 3.2.4 版本对比

**`GET /api/workflows/:id/versions/diff?v1=:v1&v2=:v2`**

**描述**：对比两个版本的节点和边的差异。

**查询参数**：

```
v1: int (必选，较小版本号)
v2: int (必选，较大版本号)
```

**业务逻辑**（`VersionService.diff_versions`）：

1. 查询工作流 + 权限检查
2. 查询 v1 和 v2 两个版本
3. 任一不存在 → 404 `VERSION_NOT_FOUND`
4. 执行 Diff 算法（详见第 6 章）
5. 返回差异结果

**响应体**：`VersionDiffResponse`

---

### 3.3 工作流校验

#### 3.3.1 校验工作流

**`POST /api/workflows/:id/validate`**

**描述**：对当前工作流进行全面校验，返回所有问题。

**业务逻辑**（`ValidationService.validate_workflow`）：

1. 查询工作流 + 权限检查
2. 依次执行以下校验（详见第 4 章）：
   - 连通性检查（`_check_connectivity`）
   - 必填项检查（`_check_required_fields`）
   - DAG 环检测（`_check_dag`）
   - 变量引用检查（`_check_variable_references`）
3. 汇总所有 issue
4. `is_valid = (error_count == 0)`

**响应体**：`ValidationResultResponse`

**示例响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "is_valid": false,
    "error_count": 2,
    "warning_count": 1,
    "issues": [
      {
        "level": "error",
        "code": "NO_START_NODE",
        "message": "工作流必须包含且仅包含一个开始节点",
        "node_id": null,
        "details": null
      },
      {
        "level": "error",
        "code": "MISSING_AGENT",
        "message": "Agent 节点 'node_agent_1' 未选择 Agent",
        "node_id": "node_agent_1",
        "details": null
      },
      {
        "level": "warning",
        "code": "UNCONNECTED_OUTPUT",
        "message": "结束节点未连接任何上游输出",
        "node_id": "node_end_1",
        "details": null
      }
    ]
  }
}
```

---

### 3.4 单节点调试

#### 3.4.1 测试单个节点

**`POST /api/workflows/:id/test-node`**

**描述**：对工作流中的单个节点进行调试执行，不运行完整工作流。

**请求体**：`NodeTestRequest`

```json
{
  "node_id": "node_agent_1",
  "node_type": "agentNode",
  "config": {
    "agent_id": "uuid-of-agent",
    "input_mapping": { "query": "${input.user_query}" },
    "output_key": "result"
  },
  "input_variables": {
    "input.user_query": "帮我写一个 React 组件"
  }
}
```

**业务逻辑**（`NodeTestService.test_node`）：

1. 查询工作流 + 权限检查（确保工作流存在且属于当前用户）
2. 根据 `node_type` 分发到对应的 `NodeExecutor`
3. 执行器执行节点逻辑
4. 记录 Token 消耗到 `model_usages` 表（如有 LLM 调用）
5. 返回执行结果

**响应体**：`NodeTestResponse`

**示例**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "output": "这是一个 React 组件的代码...",
    "duration_ms": 2350,
    "tokens_used": 1523,
    "error": null
  }
}
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 400 | `UNSUPPORTED_NODE_TYPE` | 不支持的节点类型 |
| 400 | `INVALID_NODE_CONFIG` | 节点配置不完整 |
| 408 | `NODE_EXECUTION_TIMEOUT` | 节点执行超时 |
| 500 | `NODE_EXECUTION_FAILED` | 节点执行失败 |

---

### 3.5 导入/导出

#### 3.5.1 导出工作流

**`GET /api/workflows/:id/export`**

**描述**：导出工作流为 JSON 格式（不含执行数据、API Key 等敏感信息）。

**业务逻辑**（`WorkflowService.export_workflow`）：

1. 查询工作流 + 权限检查
2. 构建导出 JSON 结构
3. 脱敏处理：移除 `published_api_key`
4. 返回导出 JSON

**响应体**：`WorkflowExportResponse`

---

#### 3.5.2 导入工作流

**`POST /api/workflows/import`**

**描述**：从 JSON 导入创建工作流。

**请求体**：`WorkflowImportRequest`

**业务逻辑**（`WorkflowService.import_workflow`）：

1. 获取当前用户
2. 从 `data` 中提取 nodes_data / edges_data
3. 确定名称：`request.name` 或 `data.name`
4. 如果同名工作流已存在，添加后缀 ` (导入)` 或 `(1)` 等
5. 创建工作流 + 初始版本 v1
6. 返回新工作流信息

**响应体**：`WorkflowImportResponse`

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 400 | `INVALID_IMPORT_FORMAT` | 导入 JSON 格式不合法 |
| 400 | `IMPORT_MISSING_FIELDS` | 缺少必填字段 |

---

### 3.6 WebSocket 接口定义（Phase 5 实现）

> **Phase 4 仅定义接口签名和消息格式，不实现。Phase 5 工作流执行引擎开发时实现。**

#### 3.6.1 WebSocket Endpoint

```
WS /api/ws/workflows/{workflow_id}/execute
```

连接参数：
- 路径参数：`workflow_id` - 工作流 ID
- 查询参数：`token` - JWT access_token（WebSocket 不支持 Header 认证）

#### 3.6.2 消息格式定义

**服务端 → 客户端（下行消息）**：

```python
# app/schemas/websocket.py

from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class WSNodeStatusMessage(BaseModel):
    """节点状态变更消息"""
    type: str = "node_status"  # 消息类型标识
    node_id: str
    status: str  # "pending" | "running" | "success" | "failed" | "skipped" | "paused"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    output: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    tokens_used: Optional[int] = None


class WSLogMessage(BaseModel):
    """实时日志消息"""
    type: str = "log"
    level: str  # "info" | "warn" | "error"
    message: str
    node_id: Optional[str] = None
    timestamp: datetime


class WSExecutionCompleteMessage(BaseModel):
    """执行完成消息"""
    type: str = "execution_complete"
    execution_id: str
    status: str  # "success" | "failed" | "paused"
    total_duration_ms: int
    total_tokens: int
    output: Optional[dict] = None


class WSErrorMessage(BaseModel):
    """错误消息"""
    type: str = "error"
    code: str
    message: str
```

**客户端 → 服务端（上行消息）**：

```python
class WSReviewActionMessage(BaseModel):
    """审核节点操作消息"""
    type: str = "review_action"
    node_id: str
    action: str  # "approve" | "reject" | "modify"
    modified_data: Optional[dict] = None  # 修改后通过时的数据
    comment: Optional[str] = None
```

---

## 4. 工作流校验引擎

### 4.1 校验总览

| 校验项 | 级别 | 说明 |
|--------|------|------|
| 开始节点唯一 | error | 必须有且仅有一个 startNode |
| 结束节点存在 | error | 至少有一个 endNode |
| 孤立节点检测 | error | 所有节点必须连通（有入边或出边，开始节点除外） |
| Agent 节点必填 | error | Agent 节点必须选择 Agent |
| 知识检索必填 | error | 必须选择知识库 |
| HTTP 节点必填 | error | 必须填写 URL |
| 代码节点必填 | error | 必须填写代码 |
| DAG 环检测 | error | 非循环节点的子图不能成环 |
| 变量引用检查 | error | `${node_id.var_name}` 中 node_id 必须存在，var_name 必须是该节点的输出变量 |

### 4.2 校验引擎架构

```python
# app/services/validation_service.py

from typing import Any
from app.schemas.workflow import ValidationIssue


class ValidationService:
    """工作流校验引擎"""

    async def validate_workflow(
        self,
        nodes_data: list[dict],
        edges_data: list[dict],
    ) -> list[ValidationIssue]:
        """
        执行全量校验，返回所有问题。
        """
        issues: list[ValidationIssue] = []

        # 1. 必填项检查
        issues.extend(self._check_required_fields(nodes_data))

        # 2. 连通性检查
        issues.extend(self._check_connectivity(nodes_data, edges_data))

        # 3. DAG 环检测（排除循环节点内部）
        issues.extend(self._check_dag(nodes_data, edges_data))

        # 4. 变量引用检查
        issues.extend(self._check_variable_references(nodes_data, edges_data))

        return issues

    def _check_required_fields(self, nodes_data: list[dict]) -> list[ValidationIssue]:
        """必填项检查"""
        issues = []

        # 开始节点检查
        start_nodes = [n for n in nodes_data if n["type"] == "startNode"]
        if len(start_nodes) == 0:
            issues.append(ValidationIssue(
                level="error",
                code="NO_START_NODE",
                message="工作流必须包含一个开始节点",
            ))
        elif len(start_nodes) > 1:
            issues.append(ValidationIssue(
                level="error",
                code="MULTIPLE_START_NODES",
                message="工作流只能包含一个开始节点",
                node_id=start_nodes[1]["id"],
            ))

        # 结束节点检查
        end_nodes = [n for n in nodes_data if n["type"] == "endNode"]
        if len(end_nodes) == 0:
            issues.append(ValidationIssue(
                level="error",
                code="NO_END_NODE",
                message="工作流至少需要一个结束节点",
            ))

        # 逐节点类型检查
        for node in nodes_data:
            node_type = node["type"]
            node_id = node["id"]
            data = node.get("data", {})

            if node_type == "agentNode":
                if not data.get("agent_id"):
                    issues.append(ValidationIssue(
                        level="error",
                        code="MISSING_AGENT",
                        message=f"Agent 节点 '{data.get('label', node_id)}' 未选择 Agent",
                        node_id=node_id,
                    ))

            elif node_type == "knowledgeRetrievalNode":
                if not data.get("knowledge_base_id"):
                    issues.append(ValidationIssue(
                        level="error",
                        code="MISSING_KB",
                        message=f"知识检索节点 '{data.get('label', node_id)}' 未选择知识库",
                        node_id=node_id,
                    ))

            elif node_type == "codeNode":
                if not data.get("code"):
                    issues.append(ValidationIssue(
                        level="error",
                        code="MISSING_CODE",
                        message=f"代码节点 '{data.get('label', node_id)}' 未编写代码",
                        node_id=node_id,
                    ))

            elif node_type == "httpNode":
                if not data.get("url"):
                    issues.append(ValidationIssue(
                        level="error",
                        code="MISSING_HTTP_URL",
                        message=f"HTTP 节点 '{data.get('label', node_id)}' 未填写 URL",
                        node_id=node_id,
                    ))

            elif node_type == "templateNode":
                if not data.get("template"):
                    issues.append(ValidationIssue(
                        level="error",
                        code="MISSING_TEMPLATE",
                        message=f"模板节点 '{data.get('label', node_id)}' 未编写模板",
                        node_id=node_id,
                    ))

            elif node_type == "conditionNode":
                if not data.get("conditions"):
                    issues.append(ValidationIssue(
                        level="error",
                        code="MISSING_CONDITIONS",
                        message=f"条件分支节点 '{data.get('label', node_id)}' 未配置条件",
                        node_id=node_id,
                    ))

        return issues
```

### 4.3 连通性检查算法

```python
def _check_connectivity(
    self,
    nodes_data: list[dict],
    edges_data: list[dict],
) -> list[ValidationIssue]:
    """
    连通性检查：所有节点必须在工作流中连通（通过边连接）。
    开始节点只有出边，结束节点只有入边，其余节点必须既有入边也有出边。
    
    算法：
    1. 构建邻接表（有向图）
    2. 从开始节点出发，BFS/DFS 遍历
    3. 记录所有可达节点
    4. 对比全部节点，不可达的即为孤立节点
    """
    issues = []
    
    if not nodes_data:
        return issues

    node_ids = {n["id"] for n in nodes_data}
    
    # 构建邻接表
    adjacency: dict[str, set[str]] = {nid: set() for nid in node_ids}
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
    
    for edge in (edges_data or []):
        source = edge.get("source")
        target = edge.get("target")
        if source in node_ids and target in node_ids:
            adjacency[source].add(target)
            in_degree[target] = in_degree.get(target, 0) + 1

    # 从开始节点 BFS
    start_nodes = [n["id"] for n in nodes_data if n["type"] == "startNode"]
    if not start_nodes:
        return issues  # 没有开始节点，由必填项检查覆盖

    visited = set()
    queue = list(start_nodes)
    visited.update(start_nodes)

    while queue:
        current = queue.pop(0)
        for neighbor in adjacency.get(current, set()):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)

    # 找出不可达节点
    unreachable = node_ids - visited
    for nid in unreachable:
        node = next((n for n in nodes_data if n["id"] == nid), None)
        label = node["data"].get("label", nid) if node else nid
        issues.append(ValidationIssue(
            level="error",
            code="ORPHAN_NODE",
            message=f"节点 '{label}' 未与开始节点连通",
            node_id=nid,
        ))

    return issues
```

### 4.4 DAG 环检测算法

```python
def _check_dag(
    self,
    nodes_data: list[dict],
    edges_data: list[dict],
) -> list[ValidationIssue]:
    """
    DAG 环检测：使用 Kahn 算法（拓扑排序）检测环。
    循环节点 (loopNode) 内部的边不参与环检测。
    
    算法步骤（Kahn's Algorithm）：
    1. 构建有向图 + 计算每个节点的入度
    2. 将所有入度为 0 的节点加入队列
    3. 从队列取出节点，将其所有邻居的入度 -1
    4. 若邻居入度变为 0，加入队列
    5. 重复直到队列为空
    6. 如果处理过的节点数 < 总节点数，说明存在环
    """
    issues = []
    
    if not nodes_data or not edges_data:
        return issues

    node_ids = {n["id"] for n in nodes_data}
    node_type_map = {n["id"]: n["type"] for n in nodes_data}

    # 构建图（排除 loopNode 的内部回边）
    adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}

    for edge in (edges_data or []):
        source = edge.get("source")
        target = edge.get("target")
        if source in node_ids and target in node_ids:
            # 排除 loopNode 的内部回边：
            # 如果 target 是 loopNode 且 source 也是 loopNode 内部的节点，跳过
            # 简化策略：如果 source == target（自环），跳过
            if source == target:
                continue
            adjacency[source].append(target)
            in_degree[target] += 1

    # Kahn 算法
    queue = [nid for nid in node_ids if in_degree[nid] == 0]
    processed_count = 0

    while queue:
        node = queue.pop(0)
        processed_count += 1
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # 如果处理过的节点数 < 总节点数，存在环
    if processed_count < len(node_ids):
        # 找出环中的节点
        cycle_nodes = [nid for nid in node_ids if in_degree[nid] > 0]
        issues.append(ValidationIssue(
            level="error",
            code="CYCLE_DETECTED",
            message=f"检测到工作流存在循环依赖（涉及 {len(cycle_nodes)} 个节点），请检查连线",
            details={"cycle_node_ids": cycle_nodes},
        ))

    return issues
```

**Kahn 算法伪代码**：

```
function detectCycle(nodes, edges):
    // 初始化
    graph = {}           // 邻接表
    inDegree = {}        // 入度表
    
    for each node in nodes:
        graph[node.id] = []
        inDegree[node.id] = 0
    
    // 构建图
    for each edge in edges:
        graph[edge.source].append(edge.target)
        inDegree[edge.target] += 1
    
    // 初始化队列（入度为 0 的节点）
    queue = all nodes where inDegree[id] == 0
    processedCount = 0
    
    // BFS 拓扑排序
    while queue is not empty:
        node = queue.dequeue()
        processedCount++
        for each neighbor in graph[node]:
            inDegree[neighbor] -= 1
            if inDegree[neighbor] == 0:
                queue.enqueue(neighbor)
    
    // 判定
    if processedCount < nodes.length:
        cycleNodes = all nodes where inDegree[id] > 0
        return ERROR("CYCLE_DETECTED", cycleNodes)
    else:
        return OK
```

### 4.5 变量引用检查

```python
import re
from typing import Optional


def _check_variable_references(
    self,
    nodes_data: list[dict],
    edges_data: list[dict],
) -> list[ValidationIssue]:
    """
    变量引用检查：验证所有 ${node_id.var_name} 格式的引用是否合法。
    
    算法步骤：
    1. 构建「节点 ID → 输出变量列表」映射
    2. 遍历所有节点的配置，用正则提取 ${...} 引用
    3. 对每个引用：
       a. 解析 node_id 和 var_name
       b. 检查 node_id 是否存在
       c. 检查 var_name 是否在该节点的 outputs 中
    4. 收集所有非法引用
    """
    issues = []
    
    # 正则匹配 ${xxx.yyy} 或 ${env.XXX}
    VAR_PATTERN = re.compile(r'\$\{([^}]+)\}')

    # 1. 构建节点 ID → 节点 映射
    node_map = {n["id"]: n for n in nodes_data}

    # 2. 构建节点 ID → 输出变量名集合 映射
    node_outputs: dict[str, set[str]] = {}
    for node in nodes_data:
        node_id = node["id"]
        data = node.get("data", {})
        outputs = data.get("outputs", [])
        output_keys = {o["name"] for o in outputs}
        
        # 部分节点使用 output_key 作为输出变量名
        if data.get("output_key"):
            output_keys.add(data["output_key"])
        
        node_outputs[node_id] = output_keys

    # 3. 递归提取节点配置中所有 ${} 引用
    def extract_refs(obj, path=""):
        """递归遍历 dict/list，提取所有变量引用"""
        refs = []
        if isinstance(obj, str):
            matches = VAR_PATTERN.findall(obj)
            for match in matches:
                refs.append((match, path))
        elif isinstance(obj, dict):
            for key, value in obj.items():
                refs.extend(extract_refs(value, f"{path}.{key}"))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                refs.extend(extract_refs(item, f"{path}[{i}]"))
        return refs

    # 4. 遍历所有节点，检查引用
    for node in nodes_data:
        node_id = node["id"]
        data = node.get("data", {})
        label = data.get("label", node_id)

        # 提取所有需要检查的字段
        check_fields = [
            data.get("input_mapping"),
            data.get("query_template"),
            data.get("body_template"),
            data.get("template"),
        ]
        
        # 条件节点的 conditions
        if node["type"] == "conditionNode":
            for cond in data.get("conditions", []):
                check_fields.append(cond.get("variable"))

        for field_value in check_fields:
            if field_value is None:
                continue
            refs = extract_refs(field_value)
            for ref, path in refs:
                # 跳过环境变量引用
                if ref.startswith("env."):
                    continue

                # 解析 node_id.var_name
                parts = ref.split(".", 1)
                if len(parts) != 2:
                    # 格式不合法（没有 . 分隔）
                    issues.append(ValidationIssue(
                        level="error",
                        code="INVALID_VAR_FORMAT",
                        message=f"节点 '{label}' 中变量引用 '${{{ref}}}' 格式不合法，应为 ${{node_id.var_name}}",
                        node_id=node_id,
                        details={"ref": ref, "path": path},
                    ))
                    continue

                ref_node_id, ref_var_name = parts

                # 检查节点是否存在
                if ref_node_id not in node_map:
                    issues.append(ValidationIssue(
                        level="error",
                        code="VAR_NODE_NOT_FOUND",
                        message=f"节点 '{label}' 引用了不存在的节点 '{ref_node_id}'",
                        node_id=node_id,
                        details={"ref": ref, "ref_node_id": ref_node_id},
                    ))
                    continue

                # 检查变量是否存在
                available_outputs = node_outputs.get(ref_node_id, set())
                if ref_var_name not in available_outputs:
                    ref_node_label = node_map[ref_node_id]["data"].get("label", ref_node_id)
                    issues.append(ValidationIssue(
                        level="warning",  # warning 而非 error，因为变量可能是动态产生的
                        code="VAR_NOT_IN_OUTPUTS",
                        message=f"节点 '{label}' 引用的变量 '{ref_var_name}' 不在节点 '{ref_node_label}' 的输出变量中",
                        node_id=node_id,
                        details={
                            "ref": ref,
                            "ref_node_id": ref_node_id,
                            "available_outputs": list(available_outputs),
                        },
                    ))

    return issues
```

**变量引用解析伪代码**：

```
function checkVariableReferences(nodes, edges):
    issues = []
    nodeMap = map(node.id -> node) for each node
    outputMap = map(node.id -> set(node.outputs[*].name)) for each node
    
    for each node in nodes:
        refs = extractAllRefs(node.data)  // 正则提取所有 ${xxx.yyy}
        for each ref in refs:
            if ref starts with "env.":
                continue  // 环境变量，跳过
            
            [refNodeId, refVarName] = split(ref, ".", 1)
            
            if refNodeId not in nodeMap:
                issues.add(ERROR("VAR_NODE_NOT_FOUND", ref))
            else if refVarName not in outputMap[refNodeId]:
                issues.add(WARNING("VAR_NOT_IN_OUTPUTS", ref))
    
    return issues
```

### 4.6 校验结果数据结构

```python
# 校验结果汇总
{
    "is_valid": bool,           # 是否通过校验（error_count == 0）
    "error_count": int,         # 错误数量
    "warning_count": int,       # 警告数量
    "issues": [
        {
            "level": "error" | "warning",
            "code": str,        # 错误码
            "message": str,     # 可读描述
            "node_id": str?,    # 关联节点
            "details": dict?    # 附加信息
        }
    ]
}
```

---

## 5. 单节点调试执行器

### 5.1 执行器架构

```python
# app/services/node_executors/base.py

import time
from typing import Any, Optional
from abc import ABC, abstractmethod


class ExecutionContext:
    """节点执行上下文"""
    def __init__(
        self,
        workflow_id: str,
        user_id: str,
        db_session,       # AsyncSession
        redis_client,     # Redis
    ):
        self.workflow_id = workflow_id
        self.user_id = user_id
        self.db_session = db_session
        self.redis_client = redis_client


class NodeExecutionResult:
    """节点执行结果"""
    def __init__(
        self,
        output: Any = None,
        duration_ms: int = 0,
        tokens_used: Optional[int] = None,
        error: Optional[str] = None,
    ):
        self.output = output
        self.duration_ms = duration_ms
        self.tokens_used = tokens_used
        self.error = error


class BaseNodeExecutor(ABC):
    """节点执行器基类"""

    # 默认超时时间（秒）
    DEFAULT_TIMEOUT = 30

    @abstractmethod
    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        """
        执行节点逻辑。
        
        Args:
            config: 节点配置（来自 node.data）
            input_variables: 输入变量（键已解析为实际值）
            context: 执行上下文
        
        Returns:
            NodeExecutionResult
        """
        pass

    def _resolve_timeout(self, config: dict) -> int:
        """从配置中获取超时时间，有默认值"""
        return config.get("timeout", self.DEFAULT_TIMEOUT)

    def _resolve_variables(self, mapping: dict, input_variables: dict) -> dict:
        """
        根据 input_mapping 解析输入变量。
        
        mapping 示例: {"query": "${input.user_query}"}
        input_variables 示例: {"input.user_query": "hello"}
        返回: {"query": "hello"}
        """
        resolved = {}
        for key, template in mapping.items():
            if isinstance(template, str) and template.startswith("${") and template.endswith("}"):
                var_ref = template[2:-1]  # 去掉 ${ 和 }
                resolved[key] = input_variables.get(var_ref, template)
            else:
                resolved[key] = template
        return resolved
```

### 5.2 执行器注册表

```python
# app/services/node_executors/registry.py

from app.models.enums import NodeType
from .base import BaseNodeExecutor
from .agent_executor import AgentExecutor
from .knowledge_executor import KnowledgeRetrievalExecutor
from .code_executor import CodeExecutor
from .http_executor import HTTPExecutor
from .template_executor import TemplateExecutor
from .condition_executor import ConditionExecutor
from .classify_executor import ClassifyExecutor
from .extract_executor import ExtractExecutor
from .loop_executor import LoopExecutor
from .parallel_executor import ParallelExecutor
from .delay_executor import DelayExecutor
from .aggregate_executor import VariableAggregateExecutor
from .mock_executor import MockExecutor


class NodeExecutorRegistry:
    """节点执行器注册表"""

    _executors: dict[str, type[BaseNodeExecutor]] = {
        NodeType.agent.value: AgentExecutor,
        NodeType.knowledge_retrieval.value: KnowledgeRetrievalExecutor,
        NodeType.code.value: CodeExecutor,
        NodeType.http.value: HTTPExecutor,
        NodeType.template.value: TemplateExecutor,
        NodeType.condition.value: ConditionExecutor,
        NodeType.classify.value: ClassifyExecutor,
        NodeType.extract.value: ExtractExecutor,
        NodeType.loop.value: LoopExecutor,
        NodeType.parallel.value: ParallelExecutor,
        NodeType.delay.value: DelayExecutor,
        NodeType.variable_aggregate.value: VariableAggregateExecutor,
        # startNode, endNode, reviewNode, testNode → MockExecutor
        NodeType.start.value: MockExecutor,
        NodeType.end.value: MockExecutor,
        NodeType.review.value: MockExecutor,
        NodeType.test.value: MockExecutor,
    }

    @classmethod
    def get_executor(cls, node_type: str) -> BaseNodeExecutor:
        """获取节点类型的执行器实例"""
        executor_class = cls._executors.get(node_type)
        if executor_class is None:
            raise ValueError(f"Unsupported node type: {node_type}")
        return executor_class()
```

### 5.3 AgentExecutor（Agent 节点执行器）

```python
# app/services/node_executors/agent_executor.py

import time
import httpx
from typing import Any, Optional

from .base import BaseNodeExecutor, NodeExecutionResult, ExecutionContext
from app.core.encryption import decrypt_value


class AgentExecutor(BaseNodeExecutor):
    """
    Agent 节点执行器：调用 LLM API 执行 Agent 逻辑。
    
    执行流程：
    1. 根据 config.agent_id 从数据库查询 Agent 配置
    2. 查询 Agent 关联的 Model + Provider
    3. 解密 Provider 的 API Key
    4. 构建 messages（system_prompt + 用户输入）
    5. 调用 LLM API（根据 provider_type 选择不同 SDK）
    6. 返回 LLM 输出 + Token 统计
    """

    DEFAULT_TIMEOUT = 120  # Agent 调用 LLM 超时更长

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()

        try:
            # 1. 获取 Agent 配置
            agent_id = config.get("agent_id")
            if not agent_id:
                return NodeExecutionResult(error="agent_id is required", duration_ms=self._elapsed(start_time))

            agent = await self._get_agent(context, agent_id)
            if not agent:
                return NodeExecutionResult(error=f"Agent {agent_id} not found", duration_ms=self._elapsed(start_time))

            # 2. 获取模型和供应商
            model, provider = await self._get_model_and_provider(context, agent)
            if not model or not provider:
                return NodeExecutionResult(error="Model or Provider not configured", duration_ms=self._elapsed(start_time))

            # 3. 解密 API Key
            api_key = decrypt_value(provider.api_key_encrypted)

            # 4. 解析输入变量
            input_mapping = config.get("input_mapping", {})
            resolved_inputs = self._resolve_variables(input_mapping, input_variables)
            user_input = " ".join(str(v) for v in resolved_inputs.values())

            # 5. 构建 messages
            messages = []
            if agent.system_prompt:
                messages.append({"role": "system", "content": agent.system_prompt})
            messages.append({"role": "user", "content": user_input})

            # 6. 调用 LLM API
            llm_result = await self._call_llm(
                provider_type=provider.provider_type,
                api_key=api_key,
                base_url=provider.base_url,
                model_name=model.model_name,
                messages=messages,
                temperature=agent.temperature,
                max_tokens=agent.max_tokens,
                timeout=self._resolve_timeout(config),
            )

            output_key = config.get("output_key", "result")
            duration_ms = self._elapsed(start_time)

            return NodeExecutionResult(
                output={output_key: llm_result["content"]},
                duration_ms=duration_ms,
                tokens_used=llm_result.get("total_tokens"),
            )

        except httpx.TimeoutException:
            return NodeExecutionResult(error="LLM API call timed out", duration_ms=self._elapsed(start_time))
        except Exception as e:
            return NodeExecutionResult(error=str(e), duration_ms=self._elapsed(start_time))

    async def _call_llm(
        self,
        provider_type: str,
        api_key: str,
        base_url: Optional[str],
        model_name: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        timeout: int,
    ) -> dict:
        """
        根据 provider_type 调用不同的 LLM API。
        统一返回格式：{"content": str, "total_tokens": int}
        """
        if provider_type == "openai" or provider_type == "custom":
            return await self._call_openai_compatible(
                api_key=api_key,
                base_url=base_url or "https://api.openai.com/v1",
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        elif provider_type == "anthropic":
            return await self._call_anthropic(
                api_key=api_key,
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        elif provider_type == "google":
            return await self._call_google(
                api_key=api_key,
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

    async def _call_openai_compatible(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        timeout: int,
    ) -> dict:
        """调用 OpenAI 兼容 API（OpenAI 官方 + 自定义兼容接口）"""
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        return {
            "content": data["choices"][0]["message"]["content"],
            "total_tokens": data.get("usage", {}).get("total_tokens", 0),
        }

    async def _call_anthropic(self, api_key, model_name, messages, temperature, max_tokens, timeout) -> dict:
        """调用 Anthropic Claude API"""
        # 提取 system prompt
        system_prompt = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                chat_messages.append(msg)

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "max_tokens": max_tokens,
            "messages": chat_messages,
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        return {
            "content": data["content"][0]["text"],
            "total_tokens": data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0),
        }

    async def _call_google(self, api_key, model_name, messages, temperature, max_tokens, timeout) -> dict:
        """调用 Google Gemini API"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

        # 转换 messages 为 Gemini 格式
        contents = []
        system_instruction = None
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = {"parts": {"text": msg["content"]}}
            else:
                contents.append({
                    "role": "user" if msg["role"] == "user" else "model",
                    "parts": [{"text": msg["content"]}],
                })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data["candidates"][0]["content"]["parts"][0]["text"]
        total_tokens = data.get("usageMetadata", {}).get("totalTokenCount", 0)

        return {"content": content, "total_tokens": total_tokens}

    async def _get_agent(self, context, agent_id):
        """从数据库查询 Agent"""
        from sqlalchemy import select
        from app.models.agent import Agent
        result = await context.db_session.execute(select(Agent).where(Agent.id == agent_id))
        return result.scalar_one_or_none()

    async def _get_model_and_provider(self, context, agent):
        """查询 Agent 关联的模型和供应商"""
        from sqlalchemy import select
        from app.models.model_provider import LLMModel, ModelProvider
        
        if not agent.model_id:
            return None, None

        result = await context.db_session.execute(
            select(LLMModel).where(LLMModel.id == agent.model_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None, None

        result = await context.db_session.execute(
            select(ModelProvider).where(ModelProvider.id == model.provider_id)
        )
        provider = result.scalar_one_or_none()

        return model, provider

    def _elapsed(self, start_time) -> int:
        return int((time.time() - start_time) * 1000)
```

### 5.4 KnowledgeRetrievalExecutor（知识检索节点执行器）

```python
# app/services/node_executors/knowledge_executor.py

import time
from typing import Any

from .base import BaseNodeExecutor, NodeExecutionResult, ExecutionContext


class KnowledgeRetrievalExecutor(BaseNodeExecutor):
    """
    知识检索节点执行器：从向量数据库中检索相关文本块。
    
    执行流程：
    1. 根据 config.knowledge_base_id 查询知识库
    2. 解析 query_template 获取查询文本
    3. 将查询文本向量化（调用 Embedding API）
    4. 使用 pgvector 进行相似度搜索
    5. 返回 Top-K 结果
    """

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()

        try:
            kb_id = config.get("knowledge_base_id")
            if not kb_id:
                return NodeExecutionResult(error="knowledge_base_id is required", duration_ms=self._elapsed(start_time))

            # 获取查询文本
            query_template = config.get("query_template", "")
            query = self._resolve_template(query_template, input_variables)
            if not query:
                return NodeExecutionResult(error="Query text is empty", duration_ms=self._elapsed(start_time))

            top_k = config.get("top_k", 5)
            score_threshold = config.get("score_threshold", 0.0)

            # 向量化查询
            embedding = await self._get_embedding(query, context)
            if not embedding:
                return NodeExecutionResult(error="Failed to get embedding", duration_ms=self._elapsed(start_time))

            # pgvector 相似度搜索
            results = await self._vector_search(
                kb_id=kb_id,
                embedding=embedding,
                top_k=top_k,
                score_threshold=score_threshold,
                context=context,
            )

            output_key = config.get("output_key", "retrieved_docs")
            return NodeExecutionResult(
                output={output_key: results},
                duration_ms=self._elapsed(start_time),
            )

        except Exception as e:
            return NodeExecutionResult(error=str(e), duration_ms=self._elapsed(start_time))

    async def _get_embedding(self, text: str, context: ExecutionContext) -> list[float] | None:
        """调用 Embedding API 获取文本向量"""
        # TODO: Phase 3 实现时接入真实 Embedding API
        # 目前返回模拟向量用于调试
        import hashlib
        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16) % (10**6)
        return [float(hash_val + i) / 10**6 for i in range(1536)]

    async def _vector_search(
        self,
        kb_id: str,
        embedding: list[float],
        top_k: int,
        score_threshold: float,
        context: ExecutionContext,
    ) -> list[dict]:
        """使用 pgvector 进行余弦相似度搜索"""
        from sqlalchemy import text

        # pgvector 查询
        query = text("""
            SELECT 
                id, content, chunk_index,
                1 - (embedding <=> :query_embedding) AS similarity
            FROM knowledge_chunks
            WHERE knowledge_base_id = :kb_id
              AND embedding IS NOT NULL
            ORDER BY embedding <=> :query_embedding
            LIMIT :top_k
        """)

        result = await context.db_session.execute(query, {
            "query_embedding": str(embedding),
            "kb_id": kb_id,
            "top_k": top_k,
        })

        rows = result.fetchall()
        return [
            {
                "content": row.content,
                "chunk_index": row.chunk_index,
                "similarity": float(row.similarity),
            }
            for row in rows
            if float(row.similarity) >= score_threshold
        ]

    def _resolve_template(self, template: str, variables: dict) -> str:
        """解析模板字符串中的变量引用"""
        import re
        pattern = re.compile(r'\$\{([^}]+)\}')
        def replacer(match):
            var_name = match.group(1)
            if var_name.startswith("env."):
                return match.group(0)  # 环境变量在后续阶段解析
            return str(variables.get(var_name, match.group(0)))
        return pattern.sub(replacer, template)

    def _elapsed(self, start_time) -> int:
        return int((time.time() - start_time) * 1000)
```

### 5.5 CodeExecutor（代码执行节点执行器）

```python
# app/services/node_executors/code_executor.py

import time
import asyncio
import tempfile
import os
from typing import Any

from .base import BaseNodeExecutor, NodeExecutionResult, ExecutionContext


class CodeExecutor(BaseNodeExecutor):
    """
    代码执行节点执行器：在安全沙箱中执行 Python/JavaScript 代码。
    
    安全限制：
    - 最大执行时间: 30 秒
    - 禁止网络访问
    - 禁止文件系统访问（除临时目录）
    - 禁止 subprocess / os.system / eval / exec 等危险调用
    - 内存限制: 256MB
    - 禁止导入危险模块: os, sys, subprocess, socket, shutil, ctypes
    
    执行流程：
    1. 解析输入变量
    2. 将用户代码包装在安全沙箱中
    3. 执行代码（Python/JS）
    4. 捕获输出和错误
    5. 清理临时文件
    """

    DEFAULT_TIMEOUT = 30
    
    # 禁止导入的模块
    BLOCKED_MODULES = {
        "os", "sys", "subprocess", "socket", "shutil", "ctypes",
        "importlib", "signal", "resource", "multiprocessing",
        "threading", "http", "urllib", "requests", "httpx",
        "asyncio", "aiohttp", "websockets",
    }

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()

        language = config.get("language", "python")
        code = config.get("code", "")
        timeout = min(self._resolve_timeout(config), self.DEFAULT_TIMEOUT)
        input_mapping = config.get("input_mapping", {})
        resolved_inputs = self._resolve_variables(input_mapping, input_variables)

        if not code:
            return NodeExecutionResult(error="Code is empty", duration_ms=self._elapsed(start_time))

        # 安全检查
        security_check = self._security_check(code, language)
        if security_check:
            return NodeExecutionResult(error=security_check, duration_ms=self._elapsed(start_time))

        try:
            if language == "python":
                result = await self._execute_python(code, resolved_inputs, timeout)
            elif language == "javascript":
                result = await self._execute_javascript(code, resolved_inputs, timeout)
            else:
                return NodeExecutionResult(
                    error=f"Unsupported language: {language}",
                    duration_ms=self._elapsed(start_time),
                )

            output_key = config.get("output_key", "code_result")
            return NodeExecutionResult(
                output={output_key: result},
                duration_ms=self._elapsed(start_time),
            )

        except asyncio.TimeoutError:
            return NodeExecutionResult(
                error=f"Code execution timed out ({timeout}s)",
                duration_ms=self._elapsed(start_time),
            )
        except Exception as e:
            return NodeExecutionResult(error=str(e), duration_ms=self._elapsed(start_time))

    def _security_check(self, code: str, language: str) -> str | None:
        """
        代码安全检查。返回错误消息或 None（通过检查）。
        """
        if language == "python":
            # 检查危险导入
            import_lines = [line.strip() for line in code.split("\n") if line.strip().startswith(("import ", "from "))]
            for line in import_lines:
                for module in self.BLOCKED_MODULES:
                    if f"import {module}" in line or f"from {module}" in line:
                        return f"Blocked import: {module}. This module is not allowed in the sandbox."

            # 检查危险函数调用
            dangerous_patterns = [
                "__import__", "exec(", "eval(", "compile(",
                "os.system", "os.popen", "os.exec", "os.spawn",
                "subprocess.", "getattr(", "setattr(", "delattr(",
            ]
            for pattern in dangerous_patterns:
                if pattern in code:
                    return f"Blocked dangerous pattern: {pattern}"

        elif language == "javascript":
            dangerous_patterns = [
                "require(", "import(", "eval(", "Function(",
                "child_process", "fs.", "net.", "http.",
                "process.exit", "process.kill",
            ]
            for pattern in dangerous_patterns:
                if pattern in code:
                    return f"Blocked dangerous pattern: {pattern}"

        return None

    async def _execute_python(
        self,
        code: str,
        inputs: dict,
        timeout: int,
    ) -> Any:
        """
        在沙箱中执行 Python 代码。
        
        用户代码需定义 main(input_data: dict) -> dict 函数。
        沙箱调用 main 函数并返回结果。
        """
        # 包装代码：定义安全的执行环境
        wrapper_code = f"""
import json
import sys

# 用户输入
__input_data = json.loads('''{json.dumps(inputs, ensure_ascii=False)}''')

# 用户代码
{code}

# 执行并输出结果
try:
    if 'main' in dir():
        __result = main(__input_data)
    else:
        __result = {{"error": "No main() function defined"}}
    print(json.dumps(__result, ensure_ascii=False, default=str))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
        # 在子进程中执行（隔离环境）
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", wrapper_code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=1024 * 256,  # 256KB stdout buffer
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise

        if stderr:
            error_msg = stderr.decode("utf-8", errors="replace")
            if error_msg.strip():
                return {"error": error_msg.strip()}

        output = stdout.decode("utf-8", errors="replace").strip()
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"raw_output": output}

    async def _execute_javascript(
        self,
        code: str,
        inputs: dict,
        timeout: int,
    ) -> Any:
        """在沙箱中执行 JavaScript 代码（需要 Node.js）"""
        wrapper_code = f"""
const __inputData = {json.dumps(inputs, ensure_ascii=False)};

{code}

try {{
    if (typeof main === 'function') {{
        const result = main(__inputData);
        console.log(JSON.stringify(result));
    }} else {{
        console.log(JSON.stringify({{error: "No main() function defined"}}));
    }}
}} catch (e) {{
    console.log(JSON.stringify({{error: e.message}}));
}}
"""
        proc = await asyncio.create_subprocess_exec(
            "node", "-e", wrapper_code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise

        output = stdout.decode("utf-8", errors="replace").strip()
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"raw_output": output}

    def _elapsed(self, start_time) -> int:
        return int((time.time() - start_time) * 1000)


# 需要 import json, sys 在文件顶部
import json
import sys
```

### 5.6 HTTPExecutor（HTTP 请求节点执行器）

```python
# app/services/node_executors/http_executor.py

import time
import httpx
from typing import Any
from urllib.parse import urlparse

from .base import BaseNodeExecutor, NodeExecutionResult, ExecutionContext


class HTTPExecutor(BaseNodeExecutor):
    """
    HTTP 请求节点执行器：调用外部 REST API。
    
    安全限制：
    - 禁止访问内网 IP（SSRF 防护）
    - 最大响应体: 1MB
    - 最大超时: 60 秒
    - 仅支持 HTTP/HTTPS
    
    执行流程：
    1. 解析 URL、Method、Headers、Body
    2. 解析变量引用
    3. 执行 HTTP 请求
    4. 返回响应
    """

    DEFAULT_TIMEOUT = 30
    MAX_RESPONSE_SIZE = 1024 * 1024  # 1MB

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()

        try:
            url = config.get("url", "")
            method = config.get("method", "GET").upper()
            headers = config.get("headers", {})
            body = config.get("body")
            body_template = config.get("body_template")
            timeout = min(self._resolve_timeout(config), 60)
            auth = config.get("auth", {})

            # 解析 URL 中的变量
            url = self._resolve_template(url, input_variables)

            # SSRF 检查
            ssrf_error = self._check_ssrf(url)
            if ssrf_error:
                return NodeExecutionResult(error=ssrf_error, duration_ms=self._elapsed(start_time))

            # 解析 headers 中的变量
            resolved_headers = {}
            for k, v in headers.items():
                resolved_headers[k] = self._resolve_template(str(v), input_variables)

            # 解析认证
            if auth.get("type") == "bearer":
                token = self._resolve_template(auth.get("token", ""), input_variables)
                resolved_headers["Authorization"] = f"Bearer {token}"
            elif auth.get("type") == "api_key":
                header_name = auth.get("header_name", "X-API-Key")
                key_value = self._resolve_template(auth.get("key_value", ""), input_variables)
                resolved_headers[header_name] = key_value

            # 解析 body
            request_body = None
            if body_template:
                request_body = self._resolve_template(body_template, input_variables)
            elif body:
                if isinstance(body, str):
                    request_body = self._resolve_template(body, input_variables)
                else:
                    request_body = body

            # 执行请求
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=resolved_headers,
                    content=request_body if isinstance(request_body, str) else None,
                    json=request_body if isinstance(request_body, (dict, list)) else None,
                )

            # 检查响应体大小
            content_length = len(response.content)
            if content_length > self.MAX_RESPONSE_SIZE:
                return NodeExecutionResult(
                    error=f"Response too large: {content_length} bytes (max {self.MAX_RESPONSE_SIZE})",
                    duration_ms=self._elapsed(start_time),
                )

            # 解析响应
            try:
                response_body = response.json()
            except Exception:
                response_body = response.text

            output_key = config.get("output_key", "http_response")
            return NodeExecutionResult(
                output={
                    output_key: response_body,
                    f"{output_key}_status": response.status_code,
                    f"{output_key}_headers": dict(response.headers),
                },
                duration_ms=self._elapsed(start_time),
            )

        except httpx.TimeoutException:
            return NodeExecutionResult(error="HTTP request timed out", duration_ms=self._elapsed(start_time))
        except Exception as e:
            return NodeExecutionResult(error=str(e), duration_ms=self._elapsed(start_time))

    def _check_ssrf(self, url: str) -> str | None:
        """SSRF 防护检查"""
        try:
            parsed = urlparse(url)
        except Exception:
            return "Invalid URL format"

        if parsed.scheme not in ("http", "https"):
            return "Only HTTP/HTTPS protocols are allowed"

        hostname = parsed.hostname or ""
        
        # 内网 IP 检查
        import re
        private_patterns = [
            r'^10\.', r'^172\.(1[6-9]|2\d|3[01])\.',
            r'^192\.168\.', r'^127\.', r'^169\.254\.',
            r'^0\.', r'^::1$', r'^fc00:', r'^fd00:',
            r'^localhost$',
        ]
        for pattern in private_patterns:
            if re.match(pattern, hostname, re.IGNORECASE):
                return f"Access to private network address '{hostname}' is not allowed"

        return None

    def _resolve_template(self, template: str, variables: dict) -> str:
        """解析模板字符串中的变量引用"""
        import re
        pattern = re.compile(r'\$\{([^}]+)\}')
        def replacer(match):
            var_name = match.group(1)
            if var_name.startswith("env."):
                return match.group(0)
            return str(variables.get(var_name, match.group(0)))
        return pattern.sub(replacer, template)

    def _elapsed(self, start_time) -> int:
        return int((time.time() - start_time) * 1000)
```

### 5.7 TemplateExecutor（模板转换节点执行器）

```python
# app/services/node_executors/template_executor.py

import time
from typing import Any
from jinja2 import Environment, BaseLoader, sandbox

from .base import BaseNodeExecutor, NodeExecutionResult, ExecutionContext


class TemplateExecutor(BaseNodeExecutor):
    """
    模板转换节点执行器：使用 Jinja2 渲染模板。
    
    执行流程：
    1. 获取模板字符串
    2. 解析 input_mapping 中的变量
    3. 使用 Jinja2 SandboxEnvironment 渲染
    4. 返回渲染结果
    """

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()

        try:
            template_str = config.get("template", "")
            if not template_str:
                return NodeExecutionResult(error="Template is empty", duration_ms=self._elapsed(start_time))

            # 解析输入变量
            input_mapping = config.get("input_mapping", {})
            resolved_vars = self._resolve_variables(input_mapping, input_variables)

            # 使用沙箱环境渲染（防止模板注入攻击）
            env = sandbox.SandboxedEnvironment(loader=BaseLoader())
            template = env.from_string(template_str)
            rendered = template.render(**resolved_vars)

            output_key = config.get("output_key", "rendered_text")
            return NodeExecutionResult(
                output={output_key: rendered},
                duration_ms=self._elapsed(start_time),
            )

        except Exception as e:
            return NodeExecutionResult(error=f"Template rendering failed: {str(e)}", duration_ms=self._elapsed(start_time))

    def _elapsed(self, start_time) -> int:
        return int((time.time() - start_time) * 1000)
```

### 5.8 ConditionExecutor（条件分支节点执行器）

```python
# app/services/node_executors/condition_executor.py

import re
import time
from typing import Any

from .base import BaseNodeExecutor, NodeExecutionResult, ExecutionContext


class ConditionExecutor(BaseNodeExecutor):
    """
    条件分支节点执行器：评估条件表达式，返回匹配的分支 ID。
    
    支持的操作符:
    - equals / not_equals: 精确匹配
    - contains / not_contains: 包含/不包含
    - starts_with / ends_with: 前缀/后缀匹配
    - regex: 正则匹配
    - is_empty / is_not_empty: 空/非空
    - gt / gte / lt / lte: 数值比较
    """

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()

        try:
            conditions = config.get("conditions", [])
            branches = config.get("branches", [])

            if not conditions:
                return NodeExecutionResult(error="No conditions defined", duration_ms=self._elapsed(start_time))

            # 逐个评估条件
            matched_branch_id = None
            for condition in conditions:
                variable_ref = condition.get("variable", "")
                operator = condition.get("operator", "equals")
                expected = condition.get("value")

                # 解析变量值
                actual = self._resolve_variable_ref(variable_ref, input_variables)

                # 评估条件
                if self._evaluate(actual, operator, expected):
                    # 找到对应的分支
                    cond_id = condition.get("id")
                    for branch in branches:
                        if branch.get("condition_id") == cond_id:
                            matched_branch_id = branch["id"]
                            break
                    break  # 第一个匹配的条件

            # 如果没有匹配任何条件，走默认分支
            if not matched_branch_id:
                for branch in branches:
                    if branch.get("condition_id") is None:
                        matched_branch_id = branch["id"]
                        break

            return NodeExecutionResult(
                output={"matched_branch": matched_branch_id},
                duration_ms=self._elapsed(start_time),
            )

        except Exception as e:
            return NodeExecutionResult(error=str(e), duration_ms=self._elapsed(start_time))

    def _resolve_variable_ref(self, ref: str, variables: dict) -> Any:
        """解析变量引用，支持 ${...} 格式"""
        if isinstance(ref, str) and ref.startswith("${") and ref.endswith("}"):
            var_name = ref[2:-1]
            return variables.get(var_name)
        return ref

    def _evaluate(self, actual: Any, operator: str, expected: Any) -> bool:
        """评估单个条件"""
        if operator == "equals":
            return str(actual) == str(expected)
        elif operator == "not_equals":
            return str(actual) != str(expected)
        elif operator == "contains":
            return str(expected) in str(actual)
        elif operator == "not_contains":
            return str(expected) not in str(actual)
        elif operator == "starts_with":
            return str(actual).startswith(str(expected))
        elif operator == "ends_with":
            return str(actual).endswith(str(expected))
        elif operator == "regex":
            return bool(re.search(str(expected), str(actual)))
        elif operator == "is_empty":
            return actual is None or str(actual).strip() == ""
        elif operator == "is_not_empty":
            return actual is not None and str(actual).strip() != ""
        elif operator == "gt":
            return float(actual) > float(expected)
        elif operator == "gte":
            return float(actual) >= float(expected)
        elif operator == "lt":
            return float(actual) < float(expected)
        elif operator == "lte":
            return float(actual) <= float(expected)
        else:
            return False

    def _elapsed(self, start_time) -> int:
        return int((time.time() - start_time) * 1000)
```

### 5.9 其他执行器

#### 5.9.1 ClassifyExecutor（问题分类节点）

```python
# app/services/node_executors/classify_executor.py

class ClassifyExecutor(BaseNodeExecutor):
    """
    问题分类节点执行器：使用 LLM 对输入文本进行分类。
    实际执行时复用 AgentExecutor 的 LLM 调用逻辑。
    输出: {"category_id": "cat_1", "category_label": "技术问题"}
    """
    # 执行逻辑：
    # 1. 构建分类 prompt（列出所有类别 + 描述/关键词）
    # 2. 调用 LLM 进行分类
    # 3. 解析 LLM 返回的类别 ID
    # 4. 返回 {"category_id": "...", "category_label": "..."}
```

#### 5.9.2 ExtractExecutor（参数提取节点）

```python
class ExtractExecutor(BaseNodeExecutor):
    """
    参数提取节点执行器：使用 LLM 从文本中提取结构化参数。
    输出: {"extracted_params": {"name": "张三", "email": "xxx@example.com"}}
    """
    # 执行逻辑：
    # 1. 构建提取 prompt（包含 extraction_schema）
    # 2. 调用 LLM，要求返回 JSON 格式
    # 3. 解析 JSON 结果
    # 4. 返回 {"extracted_params": {...}}
```

#### 5.9.3 LoopExecutor（循环节点）

```python
class LoopExecutor(BaseNodeExecutor):
    """
    循环节点执行器：遍历数组，模拟单节点调试时只执行一次迭代。
    输出: {"current_item": ..., "current_index": 0}
    """
```

#### 5.9.4 ParallelExecutor（并行节点）

```python
class ParallelExecutor(BaseNodeExecutor):
    """
    并行节点执行器：模拟调试时直接返回所有分支的模拟输出。
    输出: {"parallel_status": "simulated", "branches": [...]}
    """
```

#### 5.9.5 DelayExecutor（延时节点）

```python
class DelayExecutor(BaseNodeExecutor):
    """
    延时节点执行器：等待指定秒数。调试模式下最多等待 5 秒。
    """
    async def execute(self, config, input_variables, context):
        start_time = time.time()
        delay = min(config.get("delay_seconds", 1), 5)  # 调试模式最多 5 秒
        await asyncio.sleep(delay)
        return NodeExecutionResult(
            output={"delayed_seconds": delay},
            duration_ms=self._elapsed(start_time),
        )
```

#### 5.9.6 VariableAggregateExecutor（变量聚合节点）

```python
class VariableAggregateExecutor(BaseNodeExecutor):
    """
    变量聚合节点执行器：合并多个变量为统一数据结构。
    输出: {"aggregated": {"combined": [val1, val2, ...]}}
    """
    async def execute(self, config, input_variables, context):
        start_time = time.time()
        aggregations = config.get("aggregations", [])
        result = {}
        for agg in aggregations:
            name = agg.get("name", "unnamed")
            sources = agg.get("sources", [])
            mode = agg.get("mode", "array")
            
            values = []
            for src in sources:
                # 解析变量引用
                if isinstance(src, str) and src.startswith("${") and src.endswith("}"):
                    var_name = src[2:-1]
                    values.append(input_variables.get(var_name))
                else:
                    values.append(src)
            
            if mode == "array":
                result[name] = values
            elif mode == "concat":
                result[name] = "".join(str(v) for v in values)
            elif mode == "merge":
                merged = {}
                for v in values:
                    if isinstance(v, dict):
                        merged.update(v)
                result[name] = merged
        
        output_key = config.get("output_key", "aggregated")
        return NodeExecutionResult(output={output_key: result}, duration_ms=self._elapsed(start_time))
```

#### 5.9.7 MockExecutor（模拟执行器）

```python
class MockExecutor(BaseNodeExecutor):
    """
    模拟执行器：用于 startNode、endNode、reviewNode、testNode 等
    在单节点调试时不需要实际执行逻辑的节点。
    """
    async def execute(self, config, input_variables, context):
        return NodeExecutionResult(
            output={"mock": True, "node_type": config.get("_node_type", "unknown")},
            duration_ms=0,
        )
```

### 5.10 NodeTestService 完整方法

```python
# app/services/node_test_service.py

import structlog
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.node_executors.registry import NodeExecutorRegistry
from app.services.node_executors.base import ExecutionContext, NodeExecutionResult

logger = structlog.get_logger()


class NodeTestService:
    """单节点调试服务"""

    def __init__(self, db: AsyncSession, redis):
        self.db = db
        self.redis = redis

    async def test_node(
        self,
        workflow_id: UUID,
        user_id: UUID,
        node_id: str,
        node_type: str,
        config: dict,
        input_variables: dict,
    ) -> NodeExecutionResult:
        """
        执行单节点调试。
        
        1. 验证工作流存在且属于当前用户
        2. 获取执行器
        3. 构建上下文
        4. 执行节点
        5. 记录 Token 用量（如有）
        6. 返回结果
        """
        # 验证工作流
        from sqlalchemy import select
        from app.models.workflow import Workflow
        
        result = await self.db.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise ValueError("Workflow not found")
        if workflow.user_id != user_id:
            raise PermissionError("Forbidden")

        # 获取执行器
        try:
            executor = NodeExecutorRegistry.get_executor(node_type)
        except ValueError:
            raise ValueError(f"Unsupported node type: {node_type}")

        # 构建上下文
        context = ExecutionContext(
            workflow_id=str(workflow_id),
            user_id=str(user_id),
            db_session=self.db,
            redis_client=self.redis,
        )

        # 执行
        exec_result = await executor.execute(config, input_variables, context)

        # 记录 Token 用量
        if exec_result.tokens_used and exec_result.tokens_used > 0:
            await self._record_token_usage(user_id, exec_result.tokens_used)

        return exec_result

    async def _record_token_usage(self, user_id: UUID, tokens: int):
        """记录 Token 消耗到 model_usages 表"""
        # TODO: 需要知道具体使用了哪个模型，从 Agent 配置中获取
        # 简化实现：仅记录总量
        pass
```

---

## 6. 版本管理

### 6.1 VersionService 完整方法

```python
# app/services/version_service.py

import uuid
import structlog
from uuid import UUID
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import Workflow, WorkflowVersion
from app.schemas.workflow import (
    WorkflowVersionResponse,
    WorkflowVersionDetailResponse,
    VersionDiffResponse,
)

logger = structlog.get_logger()


class VersionService:
    """版本管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_version(
        self,
        workflow_id: UUID,
        version_number: int,
        nodes_data: Optional[list],
        edges_data: Optional[list],
        tag: Optional[str] = None,
    ) -> WorkflowVersion:
        """
        创建新版本。在每次工作流保存时调用。
        
        Args:
            workflow_id: 工作流 ID
            version_number: 版本号（由调用方计算）
            nodes_data: 当前节点数据快照
            edges_data: 当前边数据快照
            tag: 可选标签
        
        Returns:
            新创建的 WorkflowVersion 记录
        """
        version = WorkflowVersion(
            id=uuid.uuid4(),
            workflow_id=workflow_id,
            version_number=version_number,
            tag=tag,
            nodes_data=nodes_data,
            edges_data=edges_data,
        )
        self.db.add(version)
        await self.db.flush()
        logger.info("version_created", workflow_id=str(workflow_id), version=version_number)
        return version

    async def list_versions(
        self,
        workflow_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """
        获取版本列表，按版本号倒序。
        """
        # 查询总数
        count_result = await self.db.execute(
            select(func.count(WorkflowVersion.id)).where(
                WorkflowVersion.workflow_id == workflow_id
            )
        )
        total = count_result.scalar()

        # 分页查询
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == workflow_id)
            .order_by(WorkflowVersion.version_number.desc())
            .offset(offset)
            .limit(page_size)
        )
        versions = result.scalars().all()

        items = []
        for v in versions:
            items.append(WorkflowVersionResponse(
                id=v.id,
                workflow_id=v.workflow_id,
                version_number=v.version_number,
                tag=v.tag,
                node_count=len(v.nodes_data) if v.nodes_data else 0,
                created_at=v.created_at,
            ))

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": offset + page_size < total,
        }

    async def get_version(
        self,
        workflow_id: UUID,
        version_number: int,
    ) -> Optional[WorkflowVersion]:
        """
        获取指定版本详情。
        """
        result = await self.db.execute(
            select(WorkflowVersion).where(
                WorkflowVersion.workflow_id == workflow_id,
                WorkflowVersion.version_number == version_number,
            )
        )
        return result.scalar_one_or_none()

    async def rollback_to_version(
        self,
        workflow: Workflow,
        version_number: int,
    ) -> dict:
        """
        回滚到指定版本。
        
        逻辑：
        1. 查询目标版本
        2. 将目标版本的 nodes_data/edges_data 复制到工作流
        3. current_version += 1
        4. 创建新版本（tag = "回滚自 vX"）
        """
        # 查询目标版本
        target = await self.get_version(workflow.id, version_number)
        if not target:
            raise ValueError(f"Version {version_number} not found")

        # 更新工作流数据
        new_version_number = workflow.current_version + 1
        workflow.nodes_data = target.nodes_data
        workflow.edges_data = target.edges_data
        workflow.current_version = new_version_number

        # 创建新版本
        new_version = await self.create_version(
            workflow_id=workflow.id,
            version_number=new_version_number,
            nodes_data=target.nodes_data,
            edges_data=target.edges_data,
            tag=f"回滚自 v{version_number}",
        )

        await self.db.flush()
        logger.info(
            "version_rollback",
            workflow_id=str(workflow.id),
            from_version=version_number,
            to_version=new_version_number,
        )

        return {
            "message": f"已回滚到版本 {version_number}",
            "workflow_id": workflow.id,
            "version_number": version_number,
            "new_version_number": new_version_number,
        }

    async def diff_versions(
        self,
        workflow_id: UUID,
        v1: int,
        v2: int,
    ) -> VersionDiffResponse:
        """
        对比两个版本的差异。
        
        使用基于节点 ID 的 diff 算法：
        1. 构建 v1 和 v2 的节点 ID 集合
        2. added = v2 有但 v1 没有的节点
        3. removed = v1 有但 v2 没有的节点
        4. common = 两者都有的节点，逐个对比 data 字段
        5. 边同理（基于 source+target 对进行匹配）
        """
        version1 = await self.get_version(workflow_id, v1)
        version2 = await self.get_version(workflow_id, v2)

        if not version1 or not version2:
            raise ValueError("Version not found")

        nodes_v1 = {n["id"]: n for n in (version1.nodes_data or [])}
        nodes_v2 = {n["id"]: n for n in (version2.nodes_data or [])}

        ids_v1 = set(nodes_v1.keys())
        ids_v2 = set(nodes_v2.keys())

        # 节点 diff
        added_nodes = [nodes_v2[nid] for nid in (ids_v2 - ids_v1)]
        removed_nodes = [nodes_v1[nid] for nid in (ids_v1 - ids_v2)]
        modified_nodes = []

        for nid in (ids_v1 & ids_v2):
            n1 = nodes_v1[nid]
            n2 = nodes_v2[nid]
            if n1 != n2:
                # 找出具体修改了哪些字段
                changes = {}
                all_keys = set(list(n1.keys()) + list(n2.keys()))
                for key in all_keys:
                    if n1.get(key) != n2.get(key):
                        changes[key] = {"old": n1.get(key), "new": n2.get(key)}
                modified_nodes.append({
                    "id": nid,
                    "type": n2.get("type", n1.get("type")),
                    "label": n2.get("data", {}).get("label", ""),
                    "changes": changes,
                })

        # 边 diff（基于 source+target 对匹配）
        def edge_key(edge):
            return f"{edge.get('source')}->{edge.get('target')}:{edge.get('sourceHandle', '')}"

        edges_v1 = {edge_key(e): e for e in (version1.edges_data or [])}
        edges_v2 = {edge_key(e): e for e in (version2.edges_data or [])}

        eids_v1 = set(edges_v1.keys())
        eids_v2 = set(edges_v2.keys())

        added_edges = [edges_v2[eid] for eid in (eids_v2 - eids_v1)]
        removed_edges = [edges_v1[eid] for eid in (eids_v1 - eids_v2)]
        modified_edges = []

        for eid in (eids_v1 & eids_v2):
            e1 = edges_v1[eid]
            e2 = edges_v2[eid]
            if e1 != e2:
                modified_edges.append({
                    "id": eid,
                    "old": e1,
                    "new": e2,
                })

        return VersionDiffResponse(
            v1=v1,
            v2=v2,
            added_nodes=added_nodes,
            removed_nodes=removed_nodes,
            modified_nodes=modified_nodes,
            added_edges=added_edges,
            removed_edges=removed_edges,
            modified_edges=modified_edges,
        )
```

### 6.2 Diff 算法详解

Diff 算法核心思路：

```
function diffVersions(version1, version2):
    // 节点 Diff
    nodesV1 = map(node.id -> node) for node in version1.nodes_data
    nodesV2 = map(node.id -> node) for node in version2.nodes_data
    
    idsV1 = set(keys(nodesV1))
    idsV2 = set(keys(nodesV2))
    
    added = idsV2 - idsV1         // 新增的节点
    removed = idsV1 - idsV2       // 删除的节点
    common = idsV1 ∩ idsV2        // 两者都有的节点
    
    modified = []
    for each id in common:
        if nodesV1[id] != nodesV2[id]:
            changes = {}
            for each key in allKeys(nodesV1[id], nodesV2[id]):
                if nodesV1[id][key] != nodesV2[id][key]:
                    changes[key] = { old: nodesV1[id][key], new: nodesV2[id][key] }
            modified.append({ id, changes })
    
    // 边 Diff（同理，用 source+target 作为唯一键）
    ...
    
    return { added, removed, modified, addedEdges, removedEdges, modifiedEdges }
```

---

## 7. Service 层汇总

### 7.1 WorkflowService 完整方法

```python
# app/services/workflow_service.py

class WorkflowService:
    """工作流 CRUD 服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.version_service = VersionService(db)

    async def list_workflows(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> dict:
        """获取工作流列表"""
        # 构建查询
        query = select(Workflow).where(Workflow.user_id == user_id)
        count_query = select(func.count(Workflow.id)).where(Workflow.user_id == user_id)

        if keyword:
            like_pattern = f"%{keyword}%"
            query = query.where(
                (Workflow.name.ilike(like_pattern)) | (Workflow.description.ilike(like_pattern))
            )
            count_query = count_query.where(
                (Workflow.name.ilike(like_pattern)) | (Workflow.description.ilike(like_pattern))
            )

        # 排序
        sort_column = getattr(Workflow, sort_by, Workflow.updated_at)
        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # 分页
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        offset = (page - 1) * page_size
        result = await self.db.execute(query.offset(offset).limit(page_size))
        workflows = result.scalars().all()

        items = []
        for wf in workflows:
            items.append(WorkflowListItem(
                id=wf.id,
                name=wf.name,
                description=wf.description,
                node_count=len(wf.nodes_data) if wf.nodes_data else 0,
                current_version=wf.current_version,
                is_published_api=wf.is_published_api,
                created_at=wf.created_at,
                updated_at=wf.updated_at,
            ))

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": offset + page_size < total,
        }

    async def create_workflow(
        self,
        user_id: UUID,
        name: str,
        description: Optional[str] = None,
        nodes_data: Optional[list] = None,
        edges_data: Optional[list] = None,
    ) -> Workflow:
        """创建工作流 + 初始版本"""
        workflow = Workflow(
            user_id=user_id,
            name=name,
            description=description,
            nodes_data=nodes_data or [],
            edges_data=edges_data or [],
            current_version=1,
        )
        self.db.add(workflow)
        await self.db.flush()

        # 创建初始版本
        await self.version_service.create_version(
            workflow_id=workflow.id,
            version_number=1,
            nodes_data=workflow.nodes_data,
            edges_data=workflow.edges_data,
            tag="初始版本",
        )
        await self.db.flush()
        return workflow

    async def get_workflow(self, workflow_id: UUID, user_id: UUID) -> Workflow:
        """获取工作流详情（含权限检查）"""
        result = await self.db.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise WorkflowNotFoundError()
        if workflow.user_id != user_id:
            raise ForbiddenError()
        return workflow

    async def update_workflow(
        self,
        workflow: Workflow,
        name: Optional[str] = None,
        description: Optional[str] = None,
        nodes_data: Optional[list] = None,
        edges_data: Optional[list] = None,
    ) -> Workflow:
        """更新工作流，如有数据变更则创建新版本"""
        has_data_change = False

        if name is not None:
            workflow.name = name
        if description is not None:
            workflow.description = description
        if nodes_data is not None:
            if nodes_data != workflow.nodes_data:
                has_data_change = True
            workflow.nodes_data = nodes_data
        if edges_data is not None:
            if edges_data != workflow.edges_data:
                has_data_change = True
            workflow.edges_data = edges_data

        if has_data_change:
            new_version = workflow.current_version + 1
            workflow.current_version = new_version
            await self.version_service.create_version(
                workflow_id=workflow.id,
                version_number=new_version,
                nodes_data=workflow.nodes_data,
                edges_data=workflow.edges_data,
            )

        await self.db.flush()
        return workflow

    async def delete_workflow(self, workflow_id: UUID, user_id: UUID) -> None:
        """删除工作流"""
        workflow = await self.get_workflow(workflow_id, user_id)
        await self.db.delete(workflow)
        await self.db.flush()

    async def export_workflow(self, workflow: Workflow) -> dict:
        """导出工作流"""
        from datetime import datetime, timezone
        return {
            "id": str(workflow.id),
            "name": workflow.name,
            "description": workflow.description,
            "version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "nodes_data": workflow.nodes_data or [],
            "edges_data": workflow.edges_data or [],
            "metadata": {
                "current_version": workflow.current_version,
                "node_count": len(workflow.nodes_data) if workflow.nodes_data else 0,
                "edge_count": len(workflow.edges_data) if workflow.edges_data else 0,
            },
        }

    async def import_workflow(
        self,
        user_id: UUID,
        import_data: dict,
        name_override: Optional[str] = None,
    ) -> Workflow:
        """导入工作流"""
        name = name_override or import_data.get("name", "未命名工作流")
        
        # 检查同名工作流
        existing = await self.db.execute(
            select(Workflow).where(
                Workflow.user_id == user_id,
                Workflow.name == name,
            )
        )
        if existing.scalar_one_or_none():
            name = f"{name} (导入)"
            # 再次检查
            suffix = 1
            while True:
                check_name = f"{name}({suffix})"
                dup = await self.db.execute(
                    select(Workflow).where(
                        Workflow.user_id == user_id,
                        Workflow.name == check_name,
                    )
                )
                if not dup.scalar_one_or_none():
                    name = check_name
                    break
                suffix += 1

        return await self.create_workflow(
            user_id=user_id,
            name=name,
            description=import_data.get("description"),
            nodes_data=import_data.get("nodes_data", []),
            edges_data=import_data.get("edges_data", []),
        )
```

### 7.2 自定义异常类

```python
# app/core/exceptions.py — Phase 4 新增异常

class WorkflowNotFoundError(AppException):
    def __init__(self):
        super().__init__(
            code="WORKFLOW_NOT_FOUND",
            message="工作流不存在",
            status_code=404,
        )


class VersionNotFoundError(AppException):
    def __init__(self, version_number: int):
        super().__init__(
            code="VERSION_NOT_FOUND",
            message=f"版本 v{version_number} 不存在",
            status_code=404,
        )


class ForbiddenError(AppException):
    def __init__(self):
        super().__init__(
            code="FORBIDDEN",
            message="无权操作此资源",
            status_code=403,
        )


class UnsupportedNodeTypeError(AppException):
    def __init__(self, node_type: str):
        super().__init__(
            code="UNSUPPORTED_NODE_TYPE",
            message=f"不支持的节点类型: {node_type}",
            status_code=400,
        )


class NodeExecutionTimeoutError(AppException):
    def __init__(self, timeout: int):
        super().__init__(
            code="NODE_EXECUTION_TIMEOUT",
            message=f"节点执行超时（{timeout}秒）",
            status_code=408,
        )


class InvalidImportFormatError(AppException):
    def __init__(self):
        super().__init__(
            code="INVALID_IMPORT_FORMAT",
            message="导入 JSON 格式不合法",
            status_code=400,
        )
```

---

## 8. 错误码汇总

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| **通用** | | |
| 400 | `VALIDATION_ERROR` | 参数校验失败 |
| 401 | `UNAUTHORIZED` | 未登录或 Token 过期 |
| 403 | `FORBIDDEN` | 无权操作 |
| 404 | `WORKFLOW_NOT_FOUND` | 工作流不存在 |
| 404 | `VERSION_NOT_FOUND` | 版本不存在 |
| **工作流** | | |
| 400 | `INVALID_NODE_CONFIG` | 节点配置不完整 |
| 400 | `UNSUPPORTED_NODE_TYPE` | 不支持的节点类型 |
| 400 | `INVALID_IMPORT_FORMAT` | 导入 JSON 格式不合法 |
| 400 | `IMPORT_MISSING_FIELDS` | 导入数据缺少必填字段 |
| 422 | `WORKFLOW_NAME_REQUIRED` | 工作流名称必填 |
| **校验** | | |
| 200 | `NO_START_NODE` | 缺少开始节点 |
| 200 | `MULTIPLE_START_NODES` | 多个开始节点 |
| 200 | `NO_END_NODE` | 缺少结束节点 |
| 200 | `ORPHAN_NODE` | 孤立节点 |
| 200 | `CYCLE_DETECTED` | 检测到环 |
| 200 | `MISSING_AGENT` | Agent 节点未选择 Agent |
| 200 | `MISSING_KB` | 知识检索节点未选择知识库 |
| 200 | `MISSING_CODE` | 代码节点未编写代码 |
| 200 | `MISSING_HTTP_URL` | HTTP 节点未填写 URL |
| 200 | `MISSING_TEMPLATE` | 模板节点未编写模板 |
| 200 | `MISSING_CONDITIONS` | 条件节点未配置条件 |
| 200 | `INVALID_VAR_FORMAT` | 变量引用格式不合法 |
| 200 | `VAR_NODE_NOT_FOUND` | 引用了不存在的节点 |
| 200 | `VAR_NOT_IN_OUTPUTS` | 引用的变量不在节点输出中 |
| **节点调试** | | |
| 400 | `INVALID_NODE_CONFIG` | 节点配置不完整 |
| 408 | `NODE_EXECUTION_TIMEOUT` | 节点执行超时 |
| 500 | `NODE_EXECUTION_FAILED` | 节点执行失败 |

---

## 9. 与 Phase 0-3 的衔接

### 9.1 依赖关系

| 依赖 | 说明 |
|------|------|
| Phase 0 | Workflow/WorkflowVersion 基础模型、Base/TimestampMixin、异常类、数据库连接、中间件 |
| Phase 1 | 用户认证（JWT）、`get_current_user` 依赖注入 |
| Phase 2 | Agent 模型（AgentExecutor 需要查询 Agent）、LLMModel/ModelProvider（调用 LLM）、Tool 模型 |
| Phase 3 | KnowledgeBase/KnowledgeChunk（KnowledgeRetrievalExecutor 需要查询知识库和向量） |

### 9.2 目录结构变更

```
app/
├── models/
│   ├── workflow.py             # 【修改】重命名 nodes_json→nodes_data, edges_json→edges_data, 新增索引
│   └── enums.py                # 【修改】新增 NodeType 枚举
├── schemas/
│   ├── workflow.py             # 【重写】Phase 4 完整 Schema
│   └── websocket.py            # 【新增】WebSocket 消息格式（Phase 5 使用）
├── services/
│   ├── workflow_service.py     # 【新增】工作流 CRUD
│   ├── version_service.py      # 【新增】版本管理
│   ├── validation_service.py   # 【新增】工作流校验引擎
│   ├── node_test_service.py    # 【新增】单节点调试
│   └── node_executors/         # 【新增】节点执行器目录
│       ├── __init__.py
│       ├── base.py             # 基类 + 上下文 + 结果
│       ├── registry.py         # 注册表
│       ├── agent_executor.py
│       ├── knowledge_executor.py
│       ├── code_executor.py
│       ├── http_executor.py
│       ├── template_executor.py
│       ├── condition_executor.py
│       ├── classify_executor.py
│       ├── extract_executor.py
│       ├── loop_executor.py
│       ├── parallel_executor.py
│       ├── delay_executor.py
│       ├── aggregate_executor.py
│       └── mock_executor.py
├── api/
│   └── v1/
│       └── workflows.py        # 【重写】从空骨架到完整实现
└── tests/
    ├── test_workflows.py       # 【新增】
    ├── test_versions.py        # 【新增】
    ├── test_validation.py      # 【新增】
    └── test_node_executors.py  # 【新增】
```

### 9.3 路由注册

在 `app/api/router.py` 中确保工作流路由已挂载：

```python
from app.api.v1 import workflows

api_router = APIRouter(prefix="/api")
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
```

### 9.4 依赖安装

```
# requirements.txt 新增
jinja2>=3.1.0         # 模板渲染
```

---

## 10. 测试用例

### 10.1 工作流 CRUD 测试

| 编号 | 前置条件 | 步骤 | 预期结果 | 优先级 |
|------|---------|------|---------|--------|
| WF-001 | 用户已登录 | 创建工作流（name="测试工作流"） | 200，返回工作流详情，current_version=1 | P0 |
| WF-002 | 存在工作流 | GET /api/workflows | 200，返回列表，包含刚创建的工作流 | P0 |
| WF-003 | 存在工作流 | GET /api/workflows/:id | 200，返回详情含 nodes_data 和 edges_data | P0 |
| WF-004 | 存在工作流 | PUT 更新 nodes_data | 200，current_version 变为 2 | P0 |
| WF-005 | 存在工作流 | DELETE /api/workflows/:id | 200，删除成功，再次 GET 返回 404 | P0 |
| WF-006 | 用户 A 创建工作流 | 用户 B GET 该工作流 | 403 FORBIDDEN | P0 |
| WF-007 | 用户已登录 | 创建空名称工作流 | 422 VALIDATION_ERROR | P1 |
| WF-008 | 存在工作流 | 搜索 keyword="测试" | 返回名称/描述包含"测试"的工作流 | P1 |
| WF-009 | 存在多个工作流 | 按 name 排序 asc | 按名称升序返回 | P1 |

### 10.2 版本管理测试

| 编号 | 前置条件 | 步骤 | 预期结果 | 优先级 |
|------|---------|------|---------|--------|
| VER-001 | 创建工作流 | GET /versions | 返回 v1（初始版本） | P0 |
| VER-002 | 更新 2 次 | GET /versions | 返回 v1, v2, v3 三个版本 | P0 |
| VER-003 | 存在 v1-v3 | GET /versions/2 | 返回 v2 的完整 nodes_data | P0 |
| VER-004 | 存在 v1-v3 | POST /versions/1/rollback | 工作流数据恢复为 v1，产生 v4 | P0 |
| VER-005 | 存在 v1, v2 | GET /versions/diff?v1=1&v2=2 | 返回节点增删改差异 | P0 |
| VER-006 | 存在 v1 | GET /versions/999 | 404 VERSION_NOT_FOUND | P1 |

### 10.3 工作流校验测试

| 编号 | 前置条件 | 步骤 | 预期结果 | 优先级 |
|------|---------|------|---------|--------|
| VAL-001 | 空画布 | POST /validate | is_valid=false, NO_START_NODE + NO_END_NODE | P0 |
| VAL-002 | 只有开始+结束节点，已连通 | POST /validate | is_valid=true | P0 |
| VAL-003 | Agent 节点未选 Agent | POST /validate | MISSING_AGENT error | P0 |
| VAL-004 | 存在孤立节点 | POST /validate | ORPHAN_NODE error | P0 |
| VAL-005 | 存在环 A→B→C→A | POST /validate | CYCLE_DETECTED error | P0 |
| VAL-006 | 引用不存在的节点变量 | POST /validate | VAR_NODE_NOT_FOUND | P1 |
| VAL-007 | 引用不存在的输出变量 | POST /validate | VAR_NOT_IN_OUTPUTS warning | P1 |
| VAL-008 | 多个开始节点 | POST /validate | MULTIPLE_START_NODES error | P1 |

### 10.4 单节点调试测试

| 编号 | 前置条件 | 步骤 | 预期结果 | 优先级 |
|------|---------|------|---------|--------|
| DBG-001 | 存在 Agent+LLM 配置 | test-node agentNode | 返回 LLM 输出 + tokens | P0 |
| DBG-002 | - | test-node templateNode | 返回渲染后的模板文本 | P0 |
| DBG-003 | - | test-node conditionNode | 返回 matched_branch | P0 |
| DBG-004 | - | test-node codeNode (Python) | 返回代码执行结果 | P1 |
| DBG-005 | - | test-node httpNode | 返回 HTTP 响应 | P1 |
| DBG-006 | - | test-node 超时 | 408 NODE_EXECUTION_TIMEOUT | P1 |
| DBG-007 | - | test-node 不支持的类型 | 400 UNSUPPORTED_NODE_TYPE | P1 |

### 10.5 导入/导出测试

| 编号 | 前置条件 | 步骤 | 预期结果 | 优先级 |
|------|---------|------|---------|--------|
| IMP-001 | 存在工作流 | GET /export | 返回完整 JSON | P0 |
| IMP-002 | 导出的 JSON | POST /import | 创建新工作流 | P0 |
| IMP-003 | 同名工作流存在 | POST /import | 自动添加后缀 | P1 |
| IMP-004 | 非法 JSON | POST /import | 400 INVALID_IMPORT_FORMAT | P1 |

---

## 11. 给 Cursor 的额外说明

### 11.1 实现顺序建议

Cursor 应按以下顺序实现，每完成一步确保测试通过后再进行下一步：

1. **数据库迁移**：Workflow 模型字段重命名 → Alembic 迁移 → 验证
2. **Schema 定义**：`app/schemas/workflow.py` 完整定义
3. **异常类**：`app/core/exceptions.py` 新增 Phase 4 异常
4. **WorkflowService**：CRUD 方法 → 单元测试
5. **VersionService**：版本创建/列表/详情/回滚/Diff → 单元测试
6. **ValidationService**：校验引擎 → 单元测试
7. **Node Executors**：从 MockExecutor 开始，逐步实现 Template → Condition → Code → HTTP → Agent → Knowledge
8. **NodeTestService**：单节点调试服务 → 单元测试
9. **API 路由**：`app/api/v1/workflows.py` 实现所有端点 → 集成测试
10. **导入/导出**：导出和导入逻辑

### 11.2 关键注意事项

1. **JSONB 字段重命名**：Phase 0 用的是 `nodes_json` / `edges_json`，Phase 4 重命名为 `nodes_data` / `edges_data`。Alembic 迁移中使用 `op.alter_column` + `new_column_name`。

2. **自动版本创建**：工作流的 `PUT` 更新接口中，只有当 `nodes_data` 或 `edges_data` **实际发生变更**时才创建新版本（使用 Python 的 `!=` 比较 JSON 数据）。仅修改 `name` / `description` 不触发新版本。

3. **校验结果不是错误**：`POST /validate` 始终返回 200，校验结果在 `data` 中。`is_valid=false` 不代表请求失败。

4. **单节点调试的变量解析**：`input_variables` 的 key 格式为 `node_id.var_name`（如 `node_start_1.user_query`），执行器内部不需要再解析 `${}` 引用，直接使用 `input_variables` 中的值。

5. **代码执行沙箱**：`CodeExecutor` 必须在子进程中执行代码（`asyncio.create_subprocess_exec`），不能直接在主进程 `exec()`。安全限制必须严格执行。

6. **SSRF 防护**：`HTTPExecutor` 必须检查目标 URL，禁止访问内网地址。

7. **Jinja2 沙箱**：`TemplateExecutor` 必须使用 `SandboxedEnvironment`，防止模板注入。

8. **Diff 算法的节点匹配**：使用节点 `id` 作为唯一标识进行匹配。边的匹配使用 `source→target:sourceHandle` 组合作为唯一键。

9. **WebSocket 暂不实现**：`app/schemas/websocket.py` 中定义的 WebSocket 消息格式仅供 Phase 5 使用，Phase 4 不需要实现 WebSocket 连接。

10. **依赖注入**：所有 Service 通过构造函数注入 `AsyncSession` 和 `Redis`。路由层通过 FastAPI 的 `Depends()` 注入。

### 11.3 代码风格约定

- 所有 Service 方法使用 `async/await`
- 日志使用 `structlog`，格式：`logger.info("event_name", key=value)`
- 所有数据库操作使用 `await self.db.flush()` 而非 `commit()`（事务提交在路由层统一管理）
- Pydantic Schema 使用 `model_config = {"from_attributes": True}`
- 异常类继承自 `AppException`
- UUID 参数在路由层使用 `UUID` 类型，在 Pydantic Schema 中也使用 `uuid.UUID`

### 11.4 测试框架

```python
# tests/conftest.py — Phase 4 新增 fixtures

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.main import app
from app.core.database import get_db


@pytest.fixture
async def db_session():
    """测试数据库 session"""
    engine = create_async_engine("postgresql+asyncpg://test:test@localhost:5432/tangyuan_test")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def client(db_session):
    """测试 HTTP 客户端"""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def auth_headers(client):
    """获取测试用户的认证 token"""
    # 注册 + 登录获取 token
    await client.post("/api/auth/register", json={"email": "test@example.com", "password": "Test12345"})
    resp = await client.post("/api/auth/login", json={"email": "test@example.com", "password": "Test12345"})
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
```

---

## 12. 附录：完整节点类型配置参考

### 12.1 各类型节点的 config（data 字段）完整结构

| 节点类型 | 类型标识 | 特有配置字段 |
|---------|---------|-------------|
| 开始 | `startNode` | `inputs`: 输入变量定义数组 |
| 结束 | `endNode` | `output_mapping`: 输出变量映射 |
| Agent | `agentNode` | `agent_id`, `input_mapping`, `output_key` |
| 知识检索 | `knowledgeRetrievalNode` | `knowledge_base_id`, `query_template`, `top_k`, `score_threshold`, `output_key` |
| 代码执行 | `codeNode` | `language`, `code`, `input_mapping`, `output_key` |
| HTTP 请求 | `httpNode` | `method`, `url`, `headers`, `body`/`body_template`, `auth`, `timeout`, `output_key` |
| 模板转换 | `templateNode` | `template`, `input_mapping`, `output_key` |
| 条件分支 | `conditionNode` | `conditions[]`, `branches[]` |
| 并行执行 | `parallelNode` | `branches[]`, `wait_mode` |
| 循环/迭代 | `loopNode` | `loop_variable`, `item_name`, `index_name` |
| 问题分类 | `classifyNode` | `agent_id`, `input_mapping`, `categories[]` |
| 参数提取 | `extractNode` | `agent_id`, `input_mapping`, `extraction_schema[]`, `output_key` |
| 审核 | `reviewNode` | `reviewer_ids[]`, `timeout_seconds`, `on_timeout` |
| 测试 | `testNode` | `assertions[]`, `on_failure`, `retry_count` |
| 延时等待 | `delayNode` | `delay_seconds` |
| 变量聚合 | `variableAggregateNode` | `aggregations[]`, `output_key` |

### 12.2 条件操作符完整列表

| 操作符 | 说明 | 示例 |
|--------|------|------|
| `equals` | 等于 | `${node.result}` equals `"success"` |
| `not_equals` | 不等于 | `${node.result}` not_equals `"error"` |
| `contains` | 包含 | `${node.text}` contains `"关键词"` |
| `not_contains` | 不包含 | `${node.text}` not_contains `"敏感词"` |
| `starts_with` | 前缀匹配 | `${node.text}` starts_with `"http"` |
| `ends_with` | 后缀匹配 | `${node.file}` ends_with `".pdf"` |
| `regex` | 正则匹配 | `${node.email}` regex `"^[\\w.]+@[\\w.]+$"` |
| `is_empty` | 为空 | `${node.result}` is_empty |
| `is_not_empty` | 非空 | `${node.result}` is_not_empty |
| `gt` | 大于 | `${node.score}` gt `80` |
| `gte` | 大于等于 | `${node.score}` gte `60` |
| `lt` | 小于 | `${node.count}` lt `10` |
| `lte` | 小于等于 | `${node.count}` lte `100` |

### 12.3 环境变量引用

在节点配置中，可以通过 `${env.VARIABLE_NAME}` 引用在「环境变量管理」中配置的全局变量。后端在解析变量引用时，需要：

1. 检测 `${env.XXX}` 格式
2. 从 `env_variables` 表中查询变量值
3. Secret 类型变量需要解密
4. 将值注入到执行上下文中

```python
# 变量解析辅助函数
async def resolve_env_variables(value: str, db: AsyncSession, user_id: UUID) -> str:
    """解析字符串中的 ${env.XXX} 引用"""
    import re
    pattern = re.compile(r'\$\{env\.([^}]+)\}')
    
    async def replacer(match):
        var_name = match.group(1)
        from sqlalchemy import select
        from app.models.env_variable import EnvVariable
        result = await db.execute(
            select(EnvVariable).where(
                EnvVariable.user_id == user_id,
                EnvVariable.name == var_name,
            )
        )
        env_var = result.scalar_one_or_none()
        if not env_var:
            return match.group(0)  # 未找到，保持原样
        if env_var.var_type == "secret":
            from app.core.encryption import decrypt_value
            return decrypt_value(env_var.value)
        return env_var.value
    
    return await pattern.sub(replacer, value)
```

---

**文档结束**。Phase 4 后端开发完成后，工作流编辑器将具备完整的 CRUD、版本管理、校验、单节点调试和导入导出能力，为 Phase 5（工作流执行引擎 + WebSocket 实时推送）打下坚实基础。

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
