---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 4263223131904378_0/project_7661866342080954651-files/Phase7/phase7_backend.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 4263223131904378#1784021154000
    ReservedCode2: ""
---
# 汤圆的代码助手 - Phase 7 后端开发文档：Dashboard + API 发布 + 全局打磨

> **目标读者**：Cursor / AI Coding Agent  
> **版本**：Phase 7 v1.0  
> **项目代号**：`tangyuan-backend`  
> **前置条件**：Phase 0（脚手架 + 数据库模型）+ Phase 1（用户系统）+ Phase 2（Agent + 工具 + 模型管理）+ Phase 3（知识库管理）+ Phase 4（工作流编辑器）+ Phase 5（工作流执行引擎 + WebSocket）+ Phase 6（模板 + 日志 + 环境变量 + 设置）已完成

---

## 1. 目标

在 Phase 0-6 基础上完成项目收官：

- **Dashboard 统计 API**：统计概览、Token 趋势、最近工作流/执行记录
- **工作流发布为 API**：生成 API Key、endpoint URL、外部系统调用工作流
- **已发布 API 管理**：列表、脱敏查看、启用/停用、重置 Key
- **全局搜索**：跨工作流/Agent/知识库/模板的模糊搜索
- **性能优化**：数据库索引补充、Redis 缓存 Dashboard 数据
- **安全加固**：Rate Limiting、CORS 检查、请求体限制、XSS/CSRF 防护

Phase 7 完成后，用户应能：在 Dashboard 查看全局统计 → 将工作流发布为 API → 外部系统通过 API Key 调用工作流 → 全局搜索任意资源。

---

## 2. 数据库变更

### 2.1 Execution 表新增字段

Phase 0 的 `executions` 表没有记录「触发来源」，Phase 7 需要区分是用户手动执行还是通过外部 API 调用。

```sql
-- Alembic 迁移: phase7_execution_source

-- 新增 source 字段
ALTER TABLE executions
  ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'web';
-- source 枚举值: 'web' | 'api' | 'system'

-- 新增 api_key_id 字段（记录通过哪个 API Key 调用，可为空）
ALTER TABLE executions
  ADD COLUMN api_caller_workflow_id UUID NULL;

-- 添加索引
CREATE INDEX ix_executions_source ON executions (source);
CREATE INDEX ix_executions_user_started ON executions (user_id, started_at DESC);
CREATE INDEX ix_executions_workflow_started ON executions (workflow_id, started_at DESC);
```

#### 更新 SQLAlchemy 模型 `app/models/execution.py`

```python
# 在 Execution 类中新增字段

class ExecutionSource(str, enum.Enum):
    web = "web"       # 用户通过 Web 界面触发
    api = "api"       # 外部系统通过发布 API 调用
    system = "system" # 系统内部调用（如定时任务，预留）


class Execution(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "executions"

    # ... 已有字段保持不变 ...

    # Phase 7 新增
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="web",
        server_default="web",
        index=True,
    )
    api_caller_workflow_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,  # 仅 source=api 时有值
    )
```

### 2.2 Workflow 表新增统计字段

为了避免每次都聚合查询执行统计，在 `workflows` 表增加缓存统计字段。

```sql
-- Alembic 迁移: phase7_workflow_api_stats

-- API 调用统计字段
ALTER TABLE workflows
  ADD COLUMN api_call_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE workflows
  ADD COLUMN api_total_duration_ms BIGINT NOT NULL DEFAULT 0;
ALTER TABLE workflows
  ADD COLUMN api_success_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE workflows
  ADD COLUMN api_is_active BOOLEAN NOT NULL DEFAULT true;
-- api_is_active: 发布后是否处于启用状态（停用后不接受调用）
```

#### 更新 SQLAlchemy 模型 `app/models/workflow.py`

```python
class Workflow(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "workflows"

    # ... 已有字段保持不变 ...

    # Phase 7 新增 — API 发布统计
    api_call_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    api_total_duration_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    api_success_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    api_is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
```

### 2.3 性能优化索引补充

```sql
-- Alembic 迁移: phase7_performance_indexes

-- Dashboard 统计：本月执行次数聚合
CREATE INDEX ix_executions_user_month
  ON executions (user_id, started_at DESC)
  WHERE status IN ('success', 'failed');

-- 全局搜索：workflows name/description 模糊搜索优化
CREATE INDEX ix_workflows_name_trgm
  ON workflows USING gin (name gin_trgm_ops);
CREATE INDEX ix_workflows_desc_trgm
  ON workflows USING gin (description gin_trgm_ops)
  WHERE description IS NOT NULL;

-- 全局搜索：agents name/description
CREATE INDEX ix_agents_name_trgm
  ON agents USING gin (name gin_trgm_ops);

-- 全局搜索：knowledge_bases name
CREATE INDEX ix_knowledge_bases_name_trgm
  ON knowledge_bases USING gin (name gin_trgm_ops);

-- 全局搜索：templates name/description
CREATE INDEX ix_templates_name_trgm
  ON templates USING gin (name gin_trgm_ops);

-- Token 趋势：按天聚合
CREATE INDEX ix_model_usages_user_date
  ON model_usages (user_id, date DESC);

-- 已发布 API 列表查询
CREATE INDEX ix_workflows_published
  ON workflows (user_id)
  WHERE is_published_api = true;
```

**启用 pg_trgm 扩展**（Alembic 迁移开头）：

```python
def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    # ... 后续索引创建 ...
```

---

## 3. 新增文件结构

```
app/
├── api/v1/
│   ├── dashboard.py              # Dashboard 统计路由
│   ├── published_apis.py         # 已发布 API 管理路由
│   ├── search.py                 # 全局搜索路由
│   └── external_api.py           # 外部 API 调用入口（无 JWT 认证）
├── middleware/
│   ├── rate_limiter.py           # Rate limiting 中间件
│   └── security_headers.py       # 安全响应头中间件
├── services/
│   ├── dashboard_service.py      # Dashboard 统计业务逻辑
│   ├── publish_api_service.py    # API 发布业务逻辑
│   ├── search_service.py         # 全局搜索业务逻辑
│   └── external_execution.py     # 外部 API 触发执行逻辑
├── schemas/
│   ├── dashboard.py              # Dashboard 相关 Schema
│   ├── publish_api.py            # API 发布相关 Schema
│   └── search.py                 # 搜索相关 Schema
└── core/
    └── api_key_auth.py           # API Key 认证依赖（与 JWT 认证并行）
```

---

## 4. Pydantic Schema 定义

### 4.1 Dashboard Schema `app/schemas/dashboard.py`

```python
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class DashboardStatsResponse(BaseModel):
    """Dashboard 统计概览"""
    workflow_count: int
    agent_count: int
    knowledge_base_count: int
    execution_count_this_month: int
    success_rate_this_month: float  # 0.0 ~ 100.0，百分比


class TokenUsageItem(BaseModel):
    """单日 Token 消耗"""
    date: date
    total_tokens: int
    total_cost: float  # 元，保留6位小数


class TokenUsageResponse(BaseModel):
    """Token 消耗趋势"""
    items: list[TokenUsageItem]
    total_tokens: int
    total_cost: float


class RecentWorkflowItem(BaseModel):
    """最近编辑的工作流"""
    id: str
    name: str
    description: Optional[str] = None
    node_count: int = 0
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecentExecutionItem(BaseModel):
    """最近执行记录"""
    id: str
    workflow_id: str
    workflow_name: Optional[str] = None
    status: str
    source: str = "web"
    total_duration_ms: Optional[int] = None
    started_at: datetime

    model_config = {"from_attributes": True}
```

### 4.2 API 发布 Schema `app/schemas/publish_api.py`

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class PublishApiRequest(BaseModel):
    """发布为 API（无额外参数，预留扩展）"""
    pass


class PublishApiResponse(BaseModel):
    """发布成功响应"""
    workflow_id: str
    api_key: str              # 仅在发布/重置时返回完整 Key
    endpoint_url: str          # /api/published/{api_key}/run
    created_at: datetime


class UnpublishApiResponse(BaseModel):
    """取消发布响应"""
    message: str = "已取消发布"
    workflow_id: str


class ResetApiKeyResponse(BaseModel):
    """重置 API Key 响应"""
    workflow_id: str
    api_key: str               # 新的 API Key
    endpoint_url: str
    message: str = "API Key 已重置"


class PublishedApiItem(BaseModel):
    """已发布 API 列表项"""
    workflow_id: str
    workflow_name: str
    endpoint_url: str
    api_key_masked: str        # 脱敏: "sk-xxxx...xxxx"
    created_at: datetime
    call_count: int
    success_rate: float        # 百分比
    avg_duration_ms: Optional[int] = None
    is_active: bool


class PublishedApiListResponse(BaseModel):
    """已发布 API 列表"""
    items: list[PublishedApiItem]
    total: int


class TogglePublishedApiResponse(BaseModel):
    """启用/停用响应"""
    workflow_id: str
    is_active: bool
    message: str
```

### 4.3 全局搜索 Schema `app/schemas/search.py`

```python
from pydantic import BaseModel


class SearchResultItem(BaseModel):
    """搜索结果单项"""
    id: str
    name: str
    description: str | None = None
    type: str   # "workflow" | "agent" | "knowledge" | "template"
    score: float = 0.0  # 相关度评分（可选，用于排序）


class SearchResponse(BaseModel):
    """全局搜索响应 — 按类型分组"""
    query: str
    workflows: list[SearchResultItem]
    agents: list[SearchResultItem]
    knowledge_bases: list[SearchResultItem]
    templates: list[SearchResultItem]
    total: int
```

### 4.4 外部调用 Schema `app/schemas/external_api.py`

```python
from typing import Any, Optional
from pydantic import BaseModel


class ExternalApiRunRequest(BaseModel):
    """外部 API 调用请求体"""
    input: dict[str, Any]  # 工作流输入参数


class ExternalApiRunResponse(BaseModel):
    """外部 API 调用响应"""
    execution_id: str
    status: str          # "success" | "failed"
    output: Optional[dict[str, Any]] = None
    duration_ms: int
    error: Optional[str] = None
```

---

## 5. API 完整规格

### 5.1 Dashboard 统计 API

#### 5.1.1 获取统计概览

**`GET /api/dashboard/stats`**

**描述**：获取 Dashboard 首页的统计概览数据。

**认证**：JWT（需要登录）

**业务逻辑**（`DashboardService.get_stats`）：

1. 获取当前用户 `user_id`
2. 先尝试从 Redis 缓存读取：`cache_key = f"dashboard:stats:{user_id}"`
3. 缓存命中 → 直接返回
4. 缓存未命中 → 执行以下查询：

```sql
-- 工作流总数
SELECT COUNT(*) FROM workflows WHERE user_id = :user_id;

-- Agent 总数（含预置）
SELECT COUNT(*) FROM agents WHERE user_id = :user_id;

-- 知识库数
SELECT COUNT(*) FROM knowledge_bases WHERE user_id = :user_id;

-- 本月执行次数
SELECT COUNT(*) FROM executions
WHERE user_id = :user_id
  AND started_at >= date_trunc('month', NOW())
  AND status IN ('success', 'failed');

-- 本月成功率
SELECT
  COUNT(*) FILTER (WHERE status = 'success')::float / NULLIF(COUNT(*), 0) * 100
FROM executions
WHERE user_id = :user_id
  AND started_at >= date_trunc('month', NOW())
  AND status IN ('success', 'failed');
```

5. 写入 Redis 缓存，TTL = 60 秒
6. 返回结果

**响应体**：`DashboardStatsResponse`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "workflow_count": 12,
    "agent_count": 8,
    "knowledge_base_count": 3,
    "execution_count_this_month": 256,
    "success_rate_this_month": 94.5
  }
}
```

**优化策略**：使用 `sqlalchemy.func.count()` 配合 `asyncio.gather()` 并发执行 5 个查询。

```python
# app/services/dashboard_service.py

import asyncio
from datetime import datetime
from sqlalchemy import select, func, and_
from sqlalchemy.sql import extract

from app.models.workflow import Workflow
from app.models.agent import Agent
from app.models.knowledge import KnowledgeBase
from app.models.execution import Execution
from app.core.redis import get_redis
import json


class DashboardService:

    async def get_stats(self, db, user_id: str) -> dict:
        """获取 Dashboard 统计概览"""
        redis = get_redis()
        cache_key = f"dashboard:stats:{user_id}"

        # 尝试从缓存读取
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        # 并发执行 5 个统计查询
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # 查询 1: 工作流总数
        wf_query = select(func.count(Workflow.id)).where(Workflow.user_id == user_id)

        # 查询 2: Agent 总数
        agent_query = select(func.count(Agent.id)).where(Agent.user_id == user_id)

        # 查询 3: 知识库数
        kb_query = select(func.count(KnowledgeBase.id)).where(
            KnowledgeBase.user_id == user_id
        )

        # 查询 4: 本月执行次数
        exec_query = select(func.count(Execution.id)).where(
            and_(
                Execution.user_id == user_id,
                Execution.started_at >= month_start,
                Execution.status.in_(["success", "failed"]),
            )
        )

        # 查询 5: 本月成功率
        success_query = select(
            func.count(Execution.id).filter(Execution.status == "success")
        ).where(
            and_(
                Execution.user_id == user_id,
                Execution.started_at >= month_start,
                Execution.status.in_(["success", "failed"]),
            )
        )
        total_query = select(func.count(Execution.id)).where(
            and_(
                Execution.user_id == user_id,
                Execution.started_at >= month_start,
                Execution.status.in_(["success", "failed"]),
            )
        )

        # 并发执行
        results = await asyncio.gather(
            db.execute(wf_query),
            db.execute(agent_query),
            db.execute(kb_query),
            db.execute(exec_query),
            db.execute(success_query),
            db.execute(total_query),
        )

        workflow_count = results[0].scalar() or 0
        agent_count = results[1].scalar() or 0
        kb_count = results[2].scalar() or 0
        exec_count = results[3].scalar() or 0
        success_count = results[4].scalar() or 0
        total_exec = results[5].scalar() or 0

        success_rate = round((success_count / total_exec * 100), 1) if total_exec > 0 else 0.0

        data = {
            "workflow_count": workflow_count,
            "agent_count": agent_count,
            "knowledge_base_count": kb_count,
            "execution_count_this_month": exec_count,
            "success_rate_this_month": success_rate,
        }

        # 写入缓存，TTL 60 秒
        await redis.setex(cache_key, 60, json.dumps(data, default=str))

        return data
```

---

#### 5.1.2 获取 Token 消耗趋势

**`GET /api/dashboard/token-usage?days=7`**

**描述**：获取近 N 天的 Token 消耗趋势（按天聚合）。

**认证**：JWT（需要登录）

**查询参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| days | int | 7 | 查询天数范围（1-90） |

**业务逻辑**（`DashboardService.get_token_usage`）：

1. 计算起始日期：`start_date = today - (days - 1) days`
2. 从 Redis 缓存读取：`cache_key = f"dashboard:token_usage:{user_id}:{days}"`
3. 缓存未命中 → 查询 `model_usages` 表：

```sql
SELECT
  date,
  SUM(input_tokens + output_tokens) AS total_tokens,
  SUM(cost) AS total_cost
FROM model_usages
WHERE user_id = :user_id
  AND date >= :start_date
  AND date <= :end_date
GROUP BY date
ORDER BY date ASC;
```

4. 补齐无数据的日期（填充 `total_tokens=0, total_cost=0`）
5. 写入缓存，TTL = 60 秒

**响应体**：`TokenUsageResponse`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {"date": "2026-07-08", "total_tokens": 15234, "total_cost": 0.23},
      {"date": "2026-07-09", "total_tokens": 0, "total_cost": 0.0},
      {"date": "2026-07-10", "total_tokens": 48920, "total_cost": 0.72},
      {"date": "2026-07-11", "total_tokens": 8432, "total_cost": 0.12},
      {"date": "2026-07-12", "total_tokens": 22100, "total_cost": 0.33},
      {"date": "2026-07-13", "total_tokens": 61500, "total_cost": 0.91},
      {"date": "2026-07-14", "total_tokens": 3420, "total_cost": 0.05}
    ],
    "total_tokens": 159606,
    "total_cost": 2.36
  }
}
```

**Service 实现**：

```python
from datetime import date, timedelta

async def get_token_usage(self, db, user_id: str, days: int = 7) -> dict:
    """获取 Token 消耗趋势"""
    redis = get_redis()
    cache_key = f"dashboard:token_usage:{user_id}:{days}"

    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    query = (
        select(
            ModelUsage.date,
            func.sum(ModelUsage.input_tokens + ModelUsage.output_tokens).label("total_tokens"),
            func.sum(ModelUsage.cost).label("total_cost"),
        )
        .where(
            and_(
                ModelUsage.user_id == user_id,
                ModelUsage.date >= start_date,
                ModelUsage.date <= end_date,
            )
        )
        .group_by(ModelUsage.date)
        .order_by(ModelUsage.date.asc())
    )

    result = await db.execute(query)
    rows = result.all()

    # 构建日期 → 数据映射
    data_map = {row.date: {"total_tokens": row.total_tokens, "total_cost": float(row.total_cost)} for row in rows}

    # 补齐无数据的日期
    items = []
    current = start_date
    total_tokens = 0
    total_cost = 0.0
    while current <= end_date:
        day_data = data_map.get(current, {"total_tokens": 0, "total_cost": 0.0})
        items.append({
            "date": current.isoformat(),
            "total_tokens": day_data["total_tokens"],
            "total_cost": round(day_data["total_cost"], 6),
        })
        total_tokens += day_data["total_tokens"]
        total_cost += day_data["total_cost"]
        current += timedelta(days=1)

    response = {
        "items": items,
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 6),
    }

    await redis.setex(cache_key, 60, json.dumps(response, default=str))
    return response
```

---

#### 5.1.3 获取最近编辑的工作流

**`GET /api/dashboard/recent-workflows?limit=5`**

**描述**：获取最近编辑的工作流列表。

**认证**：JWT（需要登录）

**查询参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| limit | int | 5 | 返回数量（1-20） |

**业务逻辑**（`DashboardService.get_recent_workflows`）：

1. 查询 `workflows` 表，按 `updated_at DESC` 排序，取 `limit` 条
2. 计算每条的 `node_count`

```sql
SELECT id, name, description, updated_at
FROM workflows
WHERE user_id = :user_id
ORDER BY updated_at DESC
LIMIT :limit;
```

3. `node_count` 在 ORM 层计算：`len(workflow.nodes_data) if workflow.nodes_data else 0`

**响应体**：

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "id": "uuid",
      "name": "代码审查工作流",
      "description": "自动进行 Code Review",
      "node_count": 8,
      "updated_at": "2026-07-14T15:30:00Z"
    }
  ]
}
```

---

#### 5.1.4 获取最近执行记录

**`GET /api/dashboard/recent-executions?limit=5`**

**描述**：获取最近的执行记录。

**认证**：JWT（需要登录）

**查询参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| limit | int | 5 | 返回数量（1-20） |

**业务逻辑**（`DashboardService.get_recent_executions`）：

1. 查询 `executions` 表，按 `started_at DESC` 排序，取 `limit` 条
2. 关联查询 `workflow_name`

```sql
SELECT
  e.id, e.workflow_id, w.name as workflow_name,
  e.status, e.source, e.total_duration_ms, e.started_at
FROM executions e
LEFT JOIN workflows w ON w.id = e.workflow_id
WHERE e.user_id = :user_id
ORDER BY e.started_at DESC
LIMIT :limit;
```

**响应体**：

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "id": "uuid",
      "workflow_id": "uuid",
      "workflow_name": "代码审查工作流",
      "status": "success",
      "source": "web",
      "total_duration_ms": 3420,
      "started_at": "2026-07-14T16:00:00Z"
    }
  ]
}
```

---

### 5.2 工作流发布为 API

#### 5.2.1 发布工作流为 API

**`POST /api/workflows/:id/publish-api`**

**描述**：将指定工作流发布为外部可调用的 API。

**认证**：JWT（需要登录）

**路径参数**：`id` — 工作流 UUID

**业务逻辑**（`PublishApiService.publish_api`）：

1. 查询工作流 + 权限检查（`workflow.user_id == current_user.id`）
2. 校验工作流是否可发布：
   - 工作流不能为空画布（至少有 1 个节点）
   - 工作流已有 `is_published_api = true` → 返回当前 API 信息（幂等）
3. 生成 API Key（详见 5.2.4）
4. 更新工作流：
   - `is_published_api = true`
   - `published_api_key = generated_key`
   - `api_is_active = true`
5. 清除相关缓存
6. 返回 API 信息

**响应体**：`PublishApiResponse`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "workflow_id": "uuid",
    "api_key": "sk-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
    "endpoint_url": "/api/published/sk-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6/run",
    "created_at": "2026-07-14T18:00:00Z"
  }
}
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `WORKFLOW_NOT_FOUND` | 工作流不存在 |
| 403 | `FORBIDDEN` | 无权操作 |
| 400 | `EMPTY_WORKFLOW` | 工作流画布为空，无法发布 |

---

#### 5.2.2 取消发布

**`DELETE /api/workflows/:id/publish-api`**

**描述**：取消工作流的 API 发布，外部调用将返回 401。

**认证**：JWT（需要登录）

**业务逻辑**（`PublishApiService.unpublish_api`）：

1. 查询工作流 + 权限检查
2. 校验 `is_published_api == true`，否则返回 400 `NOT_PUBLISHED`
3. 更新工作流：
   - `is_published_api = false`
   - `published_api_key = None`
   - 保留统计数据（不清零）
4. 清除 Redis 中该 API Key 的缓存
5. 返回确认

**响应体**：`UnpublishApiResponse`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "已取消发布",
    "workflow_id": "uuid"
  }
}
```

---

#### 5.2.3 重置 API Key

**`POST /api/workflows/:id/publish-api/reset-key`**

**描述**：重置 API Key，旧 Key 立即失效。

**认证**：JWT（需要登录）

**业务逻辑**（`PublishApiService.reset_api_key`）：

1. 查询工作流 + 权限检查
2. 校验 `is_published_api == true`
3. 生成新的 API Key
4. 清除旧 API Key 的 Redis 缓存
5. 更新 `published_api_key = new_key`
6. 返回新 Key

**响应体**：`ResetApiKeyResponse`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "workflow_id": "uuid",
    "api_key": "sk-x9y8z7w6v5u4t3s2r1q0p9o8n7m6l5k4",
    "endpoint_url": "/api/published/sk-x9y8z7w6v5u4t3s2r1q0p9o8n7m6l5k4/run",
    "message": "API Key 已重置"
  }
}
```

---

#### 5.2.4 API Key 生成算法

```python
# app/core/api_key_auth.py

import secrets
import hashlib
import uuid

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

from app.core.redis import get_redis


# API Key 前缀
API_KEY_PREFIX = "sk-"

# API Key 长度（不含前缀）：32 字符
API_KEY_LENGTH = 32

# 字符集：小写字母 + 数字
API_KEY_CHARSET = "abcdefghijklmnopqrstuvwxyz0123456789"


def generate_api_key() -> str:
    """
    生成 API Key。
    
    格式：sk-{32位随机字符}
    示例：sk-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
    
    算法：使用 secrets.token_hex(16) 生成 32 位十六进制字符串
    - secrets 模块使用操作系统级别的随机源（/dev/urandom）
    - token_hex(16) 产生 16 字节 = 32 位十六进制字符
    - 碰撞概率：2^128，在可预见的安全周期内不会碰撞
    """
    random_part = secrets.token_hex(16)  # 32 字符
    return f"{API_KEY_PREFIX}{random_part}"


def mask_api_key(api_key: str) -> str:
    """
    API Key 脱敏显示。
    
    规则：显示前 6 位 + "..." + 后 4 位
    示例：sk-a1b2...o5p6
    """
    if not api_key or len(api_key) < 10:
        return "****"
    return f"{api_key[:6]}...{api_key[-4:]}"


def hash_api_key(api_key: str) -> str:
    """
    对 API Key 做 SHA-256 哈希，用于 Redis 缓存键。
    
    原因：避免在 Redis 中直接存储 API Key 明文。
    查询时先哈希再查缓存。
    """
    return hashlib.sha256(api_key.encode()).hexdigest()[:32]


# ==================== API Key 认证依赖 ====================

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_api_key_from_header(
    api_key: str | None = Security(api_key_header),
) -> str:
    """
    从 X-API-Key Header 中提取 API Key。
    也支持从 Authorization: Bearer {api_key} 中提取。
    """
    if api_key:
        return api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "API_KEY_MISSING", "message": "缺少 API Key，请在 Header 中提供 X-API-Key"},
    )
```

**API Key 与 JWT 认证的区别**：

| 对比项 | JWT 认证 | API Key 认证 |
|--------|---------|-------------|
| **使用场景** | 前端用户登录操作 | 外部系统调用已发布的工作流 |
| **认证方式** | `Authorization: Bearer <jwt_token>` | `X-API-Key: <api_key>` |
| **有无用户身份** | 有（JWT payload 含 user_id） | 无（通过 API Key 反查工作流 → 用户） |
| **有效期** | access_token 30 分钟，refresh_token 7 天 | 长期有效，直到用户取消或重置 |
| **权限范围** | 完整的用户权限 | 仅限调用对应工作流 |
| **中间件** | `get_current_user` 依赖 | `get_api_key_workflow` 依赖 |
| **安全机制** | Token 过期 + Refresh | API Key 可随时重置 |

---

#### 5.2.5 API Key 认证中间件

```python
# app/core/api_key_auth.py（续）

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.workflow import Workflow


async def get_workflow_by_api_key(
    request: Request,
    api_key: str = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> Workflow:
    """
    通过 API Key 查找对应的工作流。
    
    认证流程：
    1. 从 Header 提取 API Key
    2. 检查 Redis 缓存（key → workflow_id 映射）
    3. 缓存未命中 → 数据库查询
    4. 校验工作流存在 + is_published_api + api_is_active
    5. 将结果缓存到 Redis（TTL = 5 分钟）
    6. 返回工作流对象
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "API_KEY_MISSING", "message": "缺少 API Key"},
        )

    # 1. 检查 Redis 缓存
    redis = get_redis()
    cache_key = f"api_key:{hash_api_key(api_key)}"
    cached_wf_id = await redis.get(cache_key)

    if cached_wf_id:
        # 从缓存获取 workflow_id，再查数据库确认活跃状态
        result = await db.execute(
            select(Workflow).where(
                Workflow.id == cached_wf_id,
                Workflow.is_published_api == True,
                Workflow.api_is_active == True,
            )
        )
        workflow = result.scalar_one_or_none()
        if workflow and workflow.published_api_key == api_key:
            return workflow
        # 缓存失效（Key 被重置或工作流已停用），删除缓存
        await redis.delete(cache_key)

    # 2. 数据库查询
    result = await db.execute(
        select(Workflow).where(
            Workflow.published_api_key == api_key,
            Workflow.is_published_api == True,
        )
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_API_KEY", "message": "无效的 API Key"},
        )

    if not workflow.api_is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "API_DISABLED", "message": "该 API 已被停用"},
        )

    # 3. 缓存结果
    await redis.setex(cache_key, 300, str(workflow.id))  # TTL 5 分钟

    # 将 workflow 关联到 request.state，供后续使用
    request.state.workflow = workflow
    request.state.api_key = api_key

    return workflow
```

---

### 5.3 已发布 API 管理

#### 5.3.1 获取已发布 API 列表

**`GET /api/published-apis`**

**描述**：获取当前用户所有已发布的工作流 API。

**认证**：JWT（需要登录）

**业务逻辑**（`PublishApiService.list_published_apis`）：

1. 查询 `workflows` 表，筛选 `is_published_api = true AND user_id = :current_user_id`
2. 对每条记录，计算统计信息：

```sql
SELECT
  w.id AS workflow_id,
  w.name AS workflow_name,
  w.published_api_key,
  w.created_at,
  w.api_call_count,
  w.api_total_duration_ms,
  w.api_success_count,
  w.api_is_active,
  CASE
    WHEN w.api_call_count > 0
    THEN ROUND(w.api_success_count::float / w.api_call_count * 100, 1)
    ELSE 0.0
  END AS success_rate,
  CASE
    WHEN w.api_call_count > 0
    THEN ROUND(w.api_total_duration_ms::float / w.api_call_count)
    ELSE NULL
  END AS avg_duration_ms
FROM workflows w
WHERE w.user_id = :user_id
  AND w.is_published_api = true
ORDER BY w.created_at DESC;
```

3. API Key 脱敏处理

**响应体**：`PublishedApiListResponse`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "workflow_id": "uuid",
        "workflow_name": "代码审查工作流",
        "endpoint_url": "/api/published/sk-a1b2...o5p6/run",
        "api_key_masked": "sk-a1b2...o5p6",
        "created_at": "2026-07-14T18:00:00Z",
        "call_count": 42,
        "success_rate": 95.2,
        "avg_duration_ms": 3200,
        "is_active": true
      }
    ],
    "total": 1
  }
}
```

---

#### 5.3.2 启用/停用已发布 API

**`PUT /api/published-apis/:workflow_id/toggle`**

**描述**：启用或停用已发布的 API。停用后外部调用返回 403。

**认证**：JWT（需要登录）

**路径参数**：`workflow_id` — 工作流 UUID

**请求体**：

```json
{
  "is_active": false  // true=启用, false=停用
}
```

**业务逻辑**（`PublishApiService.toggle_api`）：

1. 查询工作流 + 权限检查
2. 校验 `is_published_api == true`
3. 更新 `api_is_active = request.is_active`
4. 如果停用，清除 Redis 中该 API Key 的缓存
5. 返回当前状态

**响应体**：`TogglePublishedApiResponse`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "workflow_id": "uuid",
    "is_active": false,
    "message": "API 已停用"
  }
}
```

---

### 5.4 外部 API 调用接口

#### 5.4.1 外部系统调用工作流

**`POST /api/published/{api_key}/run`**

**描述**：外部系统通过 API Key 调用已发布的工作流，同步执行并返回结果。

**认证**：API Key（通过 URL 路径参数 + X-API-Key Header，二选一）

> **设计决策**：API Key 放在 URL 路径中是为了方便外部系统集成（curl、Postman 直接粘贴 URL 即可调用）。同时也支持通过 `X-API-Key` Header 传递（更安全，避免 Key 出现在日志中）。优先使用 Header 中的 Key。

**请求体**：`ExternalApiRunRequest`

```json
{
  "input": {
    "user_query": "帮我写一个 React 表格组件",
    "language": "typescript"
  }
}
```

**业务逻辑**（`ExternalExecutionService.run_workflow`）：

```python
# app/services/external_execution.py

import time
import asyncio
from typing import Any
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.workflow import Workflow
from app.models.execution import Execution, ExecutionSource
from app.core.redis import get_redis
from app.services.workflow_executor import WorkflowExecutor  # Phase 5 实现


class ExternalExecutionService:
    """外部 API 触发工作流执行"""

    # 最大超时时间：5 分钟
    MAX_TIMEOUT_SECONDS = 300

    async def run_workflow(
        self,
        db: AsyncSession,
        workflow: Workflow,
        input_data: dict[str, Any],
    ) -> dict:
        """
        同步执行工作流并返回结果。

        流程：
        1. 校验输入参数与工作流 startNode 的 inputs 定义匹配
        2. 创建 Execution 记录（source="api"）
        3. 调用 WorkflowExecutor 执行工作流
        4. 设置超时保护（asyncio.wait_for）
        5. 更新统计（api_call_count, api_total_duration_ms, api_success_count）
        6. 返回执行结果
        """
        start_time = time.time()

        # 1. 校验输入
        self._validate_input(workflow, input_data)

        # 2. 创建 Execution 记录
        execution = Execution(
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            version_number=workflow.current_version,
            status="running",
            source=ExecutionSource.api.value,
            input_data=input_data,
            started_at=datetime.utcnow(),
        )
        db.add(execution)
        await db.flush()

        try:
            # 3. 执行工作流（带超时保护）
            executor = WorkflowExecutor(db=db, redis=get_redis())

            result = await asyncio.wait_for(
                executor.execute(
                    workflow_id=workflow.id,
                    version_number=workflow.current_version,
                    input_data=input_data,
                    execution_id=execution.id,
                    user_id=workflow.user_id,
                ),
                timeout=self.MAX_TIMEOUT_SECONDS,
            )

            # 4. 更新执行记录
            duration_ms = int((time.time() - start_time) * 1000)
            execution.status = "success"
            execution.output_data = result.get("output", {})
            execution.total_duration_ms = duration_ms
            execution.total_tokens = result.get("total_tokens", 0)
            execution.total_cost = result.get("total_cost", 0)
            execution.finished_at = datetime.utcnow()

            # 5. 更新工作流统计
            await db.execute(
                update(Workflow)
                .where(Workflow.id == workflow.id)
                .values(
                    api_call_count=Workflow.api_call_count + 1,
                    api_success_count=Workflow.api_success_count + 1,
                    api_total_duration_ms=Workflow.api_total_duration_ms + duration_ms,
                )
            )

            await db.commit()

            return {
                "execution_id": str(execution.id),
                "status": "success",
                "output": result.get("output", {}),
                "duration_ms": duration_ms,
                "error": None,
            }

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            execution.status = "failed"
            execution.output_data = None
            execution.total_duration_ms = duration_ms
            execution.finished_at = datetime.utcnow()

            # 更新统计（失败也要计数）
            await db.execute(
                update(Workflow)
                .where(Workflow.id == workflow.id)
                .values(
                    api_call_count=Workflow.api_call_count + 1,
                    api_total_duration_ms=Workflow.api_total_duration_ms + duration_ms,
                )
            )

            await db.commit()

            return {
                "execution_id": str(execution.id),
                "status": "failed",
                "output": None,
                "duration_ms": duration_ms,
                "error": "工作流执行超时（超过 5 分钟）",
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            execution.status = "failed"
            execution.total_duration_ms = duration_ms
            execution.finished_at = datetime.utcnow()

            # 更新统计
            await db.execute(
                update(Workflow)
                .where(Workflow.id == workflow.id)
                .values(
                    api_call_count=Workflow.api_call_count + 1,
                    api_total_duration_ms=Workflow.api_total_duration_ms + duration_ms,
                )
            )

            await db.commit()

            return {
                "execution_id": str(execution.id),
                "status": "failed",
                "output": None,
                "duration_ms": duration_ms,
                "error": str(e),
            }

    def _validate_input(self, workflow: Workflow, input_data: dict) -> None:
        """
        校验输入参数。
        
        从 workflow.nodes_data 中找到 startNode，
        检查 input_data 的 key 是否与 startNode.inputs 的 name 匹配。
        """
        if not workflow.nodes_data:
            return

        start_nodes = [n for n in workflow.nodes_data if n.get("type") == "startNode"]
        if not start_nodes:
            return

        start_node = start_nodes[0]
        defined_inputs = start_node.get("data", {}).get("inputs", [])

        # 检查必填项
        for inp in defined_inputs:
            if inp.get("required", False) and inp["name"] not in input_data:
                from app.core.exceptions import AppException
                raise AppException(
                    code="MISSING_INPUT",
                    message=f"缺少必填输入参数: {inp['name']}",
                    status_code=400,
                )
```

**响应体**：`ExternalApiRunResponse`

成功：
```json
{
  "execution_id": "uuid",
  "status": "success",
  "output": {
    "final_answer": "这是一个 React 表格组件...",
    "references": []
  },
  "duration_ms": 3420,
  "error": null
}
```

失败：
```json
{
  "execution_id": "uuid",
  "status": "failed",
  "output": null,
  "duration_ms": 5000,
  "error": "Agent 节点执行失败: API Key 无效"
}
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 401 | `API_KEY_MISSING` | 缺少 API Key |
| 401 | `INVALID_API_KEY` | 无效的 API Key |
| 403 | `API_DISABLED` | API 已被停用 |
| 400 | `MISSING_INPUT` | 缺少必填输入参数 |
| 408 | `EXECUTION_TIMEOUT` | 执行超时 |
| 429 | `RATE_LIMITED` | 调用频率超限 |
| 500 | `EXECUTION_FAILED` | 执行失败 |

---

### 5.5 外部调用限流方案

```python
# app/services/rate_limit_service.py

from app.core.redis import get_redis


class RateLimitService:
    """
    API Key 级别限流。
    
    限流策略：
    - 每个 API Key：每分钟最多 30 次调用
    - 每个 API Key：每天最多 1000 次调用
    
    使用 Redis 滑动窗口计数。
    """

    # 每分钟限制
    PER_MINUTE_LIMIT = 30
    # 每天限制
    PER_DAY_LIMIT = 1000

    async def check_rate_limit(self, api_key: str) -> tuple[bool, dict]:
        """
        检查 API Key 是否超过限流阈值。
        
        Returns:
            (is_allowed, info)
            is_allowed: 是否允许继续
            info: {"remaining_minute": int, "remaining_day": int, "retry_after": int|None}
        """
        redis = get_redis()

        # 1. 检查每分钟限制（使用分钟级 key）
        minute_key = f"rate_limit:{api_key}:minute"
        minute_count = await redis.incr(minute_key)
        if minute_count == 1:
            await redis.expire(minute_key, 60)  # 首次写入时设置过期时间

        # 2. 检查每天限制
        day_key = f"rate_limit:{api_key}:day"
        day_count = await redis.incr(day_key)
        if day_count == 1:
            await redis.expire(day_key, 86400)

        remaining_minute = max(0, self.PER_MINUTE_LIMIT - minute_count)
        remaining_day = max(0, self.PER_DAY_LIMIT - day_count)

        if minute_count > self.PER_MINUTE_LIMIT:
            ttl = await redis.ttl(minute_key)
            return False, {
                "remaining_minute": 0,
                "remaining_day": remaining_day,
                "retry_after": max(1, ttl),
            }

        if day_count > self.PER_DAY_LIMIT:
            return False, {
                "remaining_minute": remaining_minute,
                "remaining_day": 0,
                "retry_after": 86400,
            }

        return True, {
            "remaining_minute": remaining_minute,
            "remaining_day": remaining_day,
            "retry_after": None,
        }
```

在外部调用路由中集成限流：

```python
# app/api/v1/external_api.py 中的限流检查

@router.post("/published/{api_key}/run")
async def run_published_workflow(
    api_key: str,
    request: ExternalApiRunRequest,
    workflow: Workflow = Depends(get_workflow_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    # 限流检查
    rate_limit_service = RateLimitService()
    is_allowed, limit_info = await rate_limit_service.check_rate_limit(api_key)

    if not is_allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMITED",
                "message": "调用频率超限",
                "retry_after": limit_info["retry_after"],
            },
            headers={"Retry-After": str(limit_info["retry_after"])},
        )

    # 执行工作流
    service = ExternalExecutionService()
    result = await service.run_workflow(db, workflow, request.input)

    return {"code": 0, "message": "success", "data": result}
```

---

### 5.6 全局搜索 API

#### 5.6.1 全局搜索

**`GET /api/search?q=keyword&type=workflow|agent|knowledge|template`**

**描述**：跨多种资源类型进行模糊搜索。

**认证**：JWT（需要登录）

**查询参数**：

| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| q | string | 是 | 搜索关键词（1-200 字符） |
| type | string | 否 | 限定搜索类型，不传则搜索全部 |

**业务逻辑**（`SearchService.search`）：

```python
# app/services/search_service.py

from sqlalchemy import select, or_, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import Workflow
from app.models.agent import Agent
from app.models.knowledge import KnowledgeBase
from app.models.template import Template


class SearchService:
    """全局搜索服务"""

    MAX_PER_TYPE = 5  # 每种类型最多返回 5 条

    async def search(
        self,
        db: AsyncSession,
        user_id: str,
        query: str,
        search_type: str | None = None,
    ) -> dict:
        """
        全局搜索实现。
        
        搜索方案：使用 PostgreSQL ILIKE + pg_trgm 相似度排序。
        
        对每种资源类型执行独立的 ILIKE 查询：
        WHERE name ILIKE '%keyword%' OR description ILIKE '%keyword%'
        
        使用 pg_trgm 的 similarity() 函数进行相关度排序（如果已安装 pg_trgm 扩展）。
        """
        results = {
            "workflows": [],
            "agents": [],
            "knowledge_bases": [],
            "templates": [],
        }

        keyword = f"%{query}%"
        limit = self.MAX_PER_TYPE

        tasks = []

        if search_type is None or search_type == "workflow":
            tasks.append(self._search_workflows(db, user_id, keyword, query, limit))

        if search_type is None or search_type == "agent":
            tasks.append(self._search_agents(db, user_id, keyword, query, limit))

        if search_type is None or search_type == "knowledge":
            tasks.append(self._search_knowledge_bases(db, user_id, keyword, query, limit))

        if search_type is None or search_type == "template":
            tasks.append(self._search_templates(db, keyword, query, limit))

        # 并发执行所有搜索查询
        import asyncio
        search_results = await asyncio.gather(*tasks)

        idx = 0
        if search_type is None or search_type == "workflow":
            results["workflows"] = search_results[idx]; idx += 1
        if search_type is None or search_type == "agent":
            results["agents"] = search_results[idx]; idx += 1
        if search_type is None or search_type == "knowledge":
            results["knowledge_bases"] = search_results[idx]; idx += 1
        if search_type is None or search_type == "template":
            results["templates"] = search_results[idx]; idx += 1

        total = sum(len(v) for v in results.values())

        return {
            "query": query,
            **results,
            "total": total,
        }

    async def _search_workflows(self, db, user_id, keyword, query, limit):
        """搜索工作流"""
        stmt = (
            select(
                Workflow.id,
                Workflow.name,
                Workflow.description,
                func.similarity(Workflow.name, query).label("sim"),
            )
            .where(
                and_(
                    Workflow.user_id == user_id,
                    or_(
                        Workflow.name.ilike(keyword),
                        Workflow.description.ilike(keyword),
                    ),
                )
            )
            .order_by(func.similarity(Workflow.name, query).desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return [
            {
                "id": str(row.id),
                "name": row.name,
                "description": row.description,
                "type": "workflow",
                "score": float(row.sim) if row.sim else 0.0,
            }
            for row in result.all()
        ]

    async def _search_agents(self, db, user_id, keyword, query, limit):
        """搜索 Agent"""
        stmt = (
            select(
                Agent.id,
                Agent.name,
                Agent.description,
                func.similarity(Agent.name, query).label("sim"),
            )
            .where(
                and_(
                    Agent.user_id == user_id,
                    or_(
                        Agent.name.ilike(keyword),
                        Agent.description.ilike(keyword),
                    ),
                )
            )
            .order_by(func.similarity(Agent.name, query).desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return [
            {
                "id": str(row.id),
                "name": row.name,
                "description": row.description,
                "type": "agent",
                "score": float(row.sim) if row.sim else 0.0,
            }
            for row in result.all()
        ]

    async def _search_knowledge_bases(self, db, user_id, keyword, query, limit):
        """搜索知识库"""
        stmt = (
            select(
                KnowledgeBase.id,
                KnowledgeBase.name,
                KnowledgeBase.description,
                func.similarity(KnowledgeBase.name, query).label("sim"),
            )
            .where(
                and_(
                    KnowledgeBase.user_id == user_id,
                    or_(
                        KnowledgeBase.name.ilike(keyword),
                        KnowledgeBase.description.ilike(keyword),
                    ),
                )
            )
            .order_by(func.similarity(KnowledgeBase.name, query).desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return [
            {
                "id": str(row.id),
                "name": row.name,
                "description": row.description,
                "type": "knowledge",
                "score": float(row.sim) if row.sim else 0.0,
            }
            for row in result.all()
        ]

    async def _search_templates(self, db, keyword, query, limit):
        """搜索模板（模板是公共的，不需要 user_id 过滤）"""
        stmt = (
            select(
                Template.id,
                Template.name,
                Template.description,
                func.similarity(Template.name, query).label("sim"),
            )
            .where(
                or_(
                    Template.name.ilike(keyword),
                    Template.description.ilike(keyword),
                )
            )
            .order_by(func.similarity(Template.name, query).desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return [
            {
                "id": str(row.id),
                "name": row.name,
                "description": row.description,
                "type": "template",
                "score": float(row.sim) if row.sim else 0.0,
            }
            for row in result.all()
        ]
```

**全文搜索方案选择**：

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| **ILIKE** | 简单，无需扩展 | 无法利用索引，大数据集慢 | 数据量 < 10 万 |
| **pg_trgm + GIN 索引** ✅ | 支持模糊匹配 + 索引加速 + similarity 排序 | 需要安装扩展 | 本项目的最佳选择 |
| **tsvector/tsquery** | 全文搜索功能强大 | 不支持中文分词（需 zhparser） | 英文为主的场景 |
| **Elasticsearch** | 功能最强大 | 额外基础设施依赖 | 大规模搜索需求 |

**本方案选择**：`pg_trgm` + `ILIKE` + `similarity()` 排序。原因：
1. 项目已有 PostgreSQL，无需额外基础设施
2. pg_trgm 支持中文的任意子串匹配
3. GIN 索引可加速 ILIKE 查询
4. `similarity()` 函数提供相关度排序

---

## 6. 路由定义

### 6.1 Dashboard 路由 `app/api/v1/dashboard.py`

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.dashboard import (
    DashboardStatsResponse,
    TokenUsageResponse,
    RecentWorkflowItem,
    RecentExecutionItem,
)
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=dict)
async def get_stats(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard 统计概览"""
    service = DashboardService()
    data = await service.get_stats(db, str(current_user.id))
    return {"code": 0, "message": "success", "data": data}


@router.get("/token-usage", response_model=dict)
async def get_token_usage(
    days: int = Query(default=7, ge=1, le=90),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Token 消耗趋势"""
    service = DashboardService()
    data = await service.get_token_usage(db, str(current_user.id), days)
    return {"code": 0, "message": "success", "data": data}


@router.get("/recent-workflows", response_model=dict)
async def get_recent_workflows(
    limit: int = Query(default=5, ge=1, le=20),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """最近编辑的工作流"""
    service = DashboardService()
    data = await service.get_recent_workflows(db, str(current_user.id), limit)
    return {"code": 0, "message": "success", "data": data}


@router.get("/recent-executions", response_model=dict)
async def get_recent_executions(
    limit: int = Query(default=5, ge=1, le=20),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """最近执行记录"""
    service = DashboardService()
    data = await service.get_recent_executions(db, str(current_user.id), limit)
    return {"code": 0, "message": "success", "data": data}
```

### 6.2 已发布 API 管理路由 `app/api/v1/published_apis.py`

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.services.publish_api_service import PublishApiService

router = APIRouter(prefix="/published-apis", tags=["Published APIs"])


class ToggleRequest(BaseModel):
    is_active: bool


@router.get("", response_model=dict)
async def list_published_apis(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """已发布 API 列表"""
    service = PublishApiService()
    data = await service.list_published_apis(db, str(current_user.id))
    return {"code": 0, "message": "success", "data": data}


@router.put("/{workflow_id}/toggle", response_model=dict)
async def toggle_api(
    workflow_id: str,
    request: ToggleRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """启用/停用 API"""
    service = PublishApiService()
    data = await service.toggle_api(
        db, str(current_user.id), workflow_id, request.is_active
    )
    return {"code": 0, "message": "success", "data": data}
```

### 6.3 工作流发布 API 路由（挂载到 workflows 路由）

```python
# 在 app/api/v1/workflows.py 中新增以下路由

@router.post("/{id}/publish-api", response_model=dict)
async def publish_api(
    id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发布工作流为 API"""
    service = PublishApiService()
    data = await service.publish_api(db, str(current_user.id), id)
    return {"code": 0, "message": "success", "data": data}


@router.delete("/{id}/publish-api", response_model=dict)
async def unpublish_api(
    id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """取消发布"""
    service = PublishApiService()
    data = await service.unpublish_api(db, str(current_user.id), id)
    return {"code": 0, "message": "success", "data": data}


@router.post("/{id}/publish-api/reset-key", response_model=dict)
async def reset_api_key(
    id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重置 API Key"""
    service = PublishApiService()
    data = await service.reset_api_key(db, str(current_user.id), id)
    return {"code": 0, "message": "success", "data": data}
```

### 6.4 外部 API 调用路由 `app/api/v1/external_api.py`

```python
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.api_key_auth import get_workflow_by_api_key
from app.schemas.external_api import ExternalApiRunRequest
from app.services.external_execution import ExternalExecutionService
from app.services.rate_limit_service import RateLimitService

router = APIRouter(tags=["External API"])


@router.post("/published/{api_key}/run", response_model=dict)
async def run_published_workflow(
    api_key: str,
    request: ExternalApiRunRequest,
    req: Request,
    workflow=Depends(get_workflow_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """外部系统调用已发布的工作流 API"""
    # 限流检查
    rate_limit = RateLimitService()
    is_allowed, limit_info = await rate_limit.check_rate_limit(api_key)

    if not is_allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMITED",
                "message": "调用频率超限",
                "retry_after": limit_info["retry_after"],
            },
            headers={"Retry-After": str(limit_info["retry_after"])},
        )

    # 执行工作流
    service = ExternalExecutionService()
    result = await service.run_workflow(db, workflow, request.input)

    return {"code": 0, "message": "success", "data": result}
```

### 6.5 全局搜索路由 `app/api/v1/search.py`

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.services.search_service import SearchService

router = APIRouter(tags=["Search"])


@router.get("/search", response_model=dict)
async def global_search(
    q: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    type: str | None = Query(
        default=None,
        pattern="^(workflow|agent|knowledge|template)$",
        description="限定搜索类型",
    ),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """全局搜索"""
    service = SearchService()
    data = await service.search(db, str(current_user.id), q, type)
    return {"code": 0, "message": "success", "data": data}
```

### 6.6 总路由注册更新 `app/api/router.py`

```python
# 在现有路由基础上新增 Phase 7 路由

from app.api.v1 import dashboard, published_apis, search, external_api

# Dashboard
api_router.include_router(dashboard.router, tags=["Dashboard"])

# 已发布 API 管理（需要 JWT）
api_router.include_router(published_apis.router, tags=["Published APIs"])

# 全局搜索
api_router.include_router(search.router, tags=["Search"])

# 外部 API 调用（不需要 JWT，使用 API Key 认证）
# 注意：这个路由不加 /api 前缀，因为路径是 /api/published/{api_key}/run
api_router.include_router(external_api.router, tags=["External API"])
```

---

## 7. PublishApiService 完整实现

```python
# app/services/publish_api_service.py

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.core.api_key_auth import generate_api_key, mask_api_key
from app.core.redis import get_redis
from app.models.workflow import Workflow


class PublishApiService:

    async def publish_api(
        self, db: AsyncSession, user_id: str, workflow_id: str
    ) -> dict:
        """发布工作流为 API"""
        workflow = await self._get_workflow_or_404(db, user_id, workflow_id)

        # 幂等：已经发布过
        if workflow.is_published_api:
            return {
                "workflow_id": str(workflow.id),
                "api_key": workflow.published_api_key,
                "endpoint_url": f"/api/published/{workflow.published_api_key}/run",
                "created_at": workflow.created_at,
            }

        # 校验画布不为空
        if not workflow.nodes_data or len(workflow.nodes_data) == 0:
            raise AppException(
                code="EMPTY_WORKFLOW",
                message="工作流画布为空，无法发布",
                status_code=400,
            )

        # 生成 API Key
        api_key = generate_api_key()

        # 更新工作流
        workflow.is_published_api = True
        workflow.published_api_key = api_key
        workflow.api_is_active = True
        workflow.api_call_count = 0
        workflow.api_total_duration_ms = 0
        workflow.api_success_count = 0

        await db.flush()

        return {
            "workflow_id": str(workflow.id),
            "api_key": api_key,
            "endpoint_url": f"/api/published/{api_key}/run",
            "created_at": datetime.utcnow(),
        }

    async def unpublish_api(
        self, db: AsyncSession, user_id: str, workflow_id: str
    ) -> dict:
        """取消发布"""
        workflow = await self._get_workflow_or_404(db, user_id, workflow_id)

        if not workflow.is_published_api:
            raise AppException(
                code="NOT_PUBLISHED",
                message="工作流未发布为 API",
                status_code=400,
            )

        # 清除缓存
        redis = get_redis()
        if workflow.published_api_key:
            from app.core.api_key_auth import hash_api_key
            cache_key = f"api_key:{hash_api_key(workflow.published_api_key)}"
            await redis.delete(cache_key)

        # 更新工作流
        workflow.is_published_api = False
        workflow.published_api_key = None
        # 保留统计数据不清零

        await db.flush()

        return {"message": "已取消发布", "workflow_id": str(workflow.id)}

    async def reset_api_key(
        self, db: AsyncSession, user_id: str, workflow_id: str
    ) -> dict:
        """重置 API Key"""
        workflow = await self._get_workflow_or_404(db, user_id, workflow_id)

        if not workflow.is_published_api:
            raise AppException(
                code="NOT_PUBLISHED",
                message="工作流未发布为 API",
                status_code=400,
            )

        # 清除旧 Key 缓存
        redis = get_redis()
        if workflow.published_api_key:
            from app.core.api_key_auth import hash_api_key
            old_cache_key = f"api_key:{hash_api_key(workflow.published_api_key)}"
            await redis.delete(old_cache_key)

        # 生成新 Key
        new_api_key = generate_api_key()
        workflow.published_api_key = new_api_key

        await db.flush()

        return {
            "workflow_id": str(workflow.id),
            "api_key": new_api_key,
            "endpoint_url": f"/api/published/{new_api_key}/run",
            "message": "API Key 已重置",
        }

    async def list_published_apis(
        self, db: AsyncSession, user_id: str
    ) -> dict:
        """获取已发布 API 列表"""
        stmt = (
            select(Workflow)
            .where(
                and_(
                    Workflow.user_id == user_id,
                    Workflow.is_published_api == True,
                )
            )
            .order_by(Workflow.created_at.desc())
        )
        result = await db.execute(stmt)
        workflows = result.scalars().all()

        items = []
        for wf in workflows:
            call_count = wf.api_call_count or 0
            success_count = wf.api_success_count or 0
            total_duration = wf.api_total_duration_ms or 0

            success_rate = round(success_count / call_count * 100, 1) if call_count > 0 else 0.0
            avg_duration = round(total_duration / call_count) if call_count > 0 else None

            items.append({
                "workflow_id": str(wf.id),
                "workflow_name": wf.name,
                "endpoint_url": f"/api/published/{mask_api_key(wf.published_api_key)}/run",
                "api_key_masked": mask_api_key(wf.published_api_key),
                "created_at": wf.created_at,
                "call_count": call_count,
                "success_rate": success_rate,
                "avg_duration_ms": avg_duration,
                "is_active": wf.api_is_active,
            })

        return {"items": items, "total": len(items)}

    async def toggle_api(
        self, db: AsyncSession, user_id: str, workflow_id: str, is_active: bool
    ) -> dict:
        """启用/停用 API"""
        workflow = await self._get_workflow_or_404(db, user_id, workflow_id)

        if not workflow.is_published_api:
            raise AppException(
                code="NOT_PUBLISHED",
                message="工作流未发布为 API",
                status_code=400,
            )

        workflow.api_is_active = is_active

        # 停用时清除缓存
        if not is_active and workflow.published_api_key:
            redis = get_redis()
            from app.core.api_key_auth import hash_api_key
            cache_key = f"api_key:{hash_api_key(workflow.published_api_key)}"
            await redis.delete(cache_key)

        await db.flush()

        status_text = "已启用" if is_active else "已停用"
        return {
            "workflow_id": str(workflow.id),
            "is_active": is_active,
            "message": f"API {status_text}",
        }

    async def _get_workflow_or_404(
        self, db: AsyncSession, user_id: str, workflow_id: str
    ) -> Workflow:
        """查询工作流 + 权限检查"""
        result = await db.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()

        if not workflow:
            raise NotFoundException("工作流", workflow_id)

        if str(workflow.user_id) != user_id:
            raise AppException(
                code="FORBIDDEN",
                message="无权限操作此工作流",
                status_code=403,
            )

        return workflow
```

---

## 8. 安全加固

### 8.1 Rate Limiting 中间件

```python
# app/middleware/rate_limiter.py

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.redis import get_redis


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    全局 Rate Limiting 中间件。
    
    策略：
    - 登录接口（/api/auth/login, /api/auth/register）：每分钟 10 次
    - API 发布接口（/api/workflows/*/publish-api）：每分钟 5 次
    - 外部调用接口（/api/published/*/run）：单独的 API Key 级别限流（在 Service 层处理）
    - 其他接口：每分钟 120 次（宽松限制，主要防滥用）
    """

    # 路由 → 限流配置
    RATE_LIMITS = {
        "auth": {"limit": 10, "window": 60},       # 认证接口
        "publish": {"limit": 5, "window": 60},      # 发布接口
        "default": {"limit": 120, "window": 60},    # 默认
    }

    async def dispatch(self, request: Request, call_next):
        # 跳过健康检查
        if request.url.path in ("/api/health", "/docs", "/redoc"):
            return await call_next(request)

        # 确定限流类别
        path = request.url.path
        if "/auth/" in path:
            category = "auth"
        elif "/publish-api" in path:
            category = "publish"
        else:
            category = "default"

        config = self.RATE_LIMITS[category]

        # 获取客户端标识（IP 或 user_id）
        client_id = self._get_client_id(request)
        rate_key = f"rate:{category}:{client_id}"

        try:
            redis = get_redis()
            count = await redis.incr(rate_key)
            if count == 1:
                await redis.expire(rate_key, config["window"])

            if count > config["limit"]:
                ttl = await redis.ttl(rate_key)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "RATE_LIMITED",
                            "message": "请求频率超限，请稍后重试",
                            "retry_after": max(1, ttl),
                        }
                    },
                    headers={
                        "Retry-After": str(max(1, ttl)),
                        "X-RateLimit-Limit": str(config["limit"]),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            # 添加限流响应头
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(config["limit"])
            response.headers["X-RateLimit-Remaining"] = str(max(0, config["limit"] - count))
            return response

        except Exception:
            # Redis 不可用时降级：不限流
            return await call_next(request)

    def _get_client_id(self, request: Request) -> str:
        """获取客户端标识，优先使用 user_id，其次 IP"""
        # 如果有 JWT 认证信息
        if hasattr(request.state, "user_id"):
            return str(request.state.user_id)
        # 使用客户端 IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
```

### 8.2 安全响应头中间件

```python
# app/middleware/security_headers.py

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    添加安全响应头，防止常见 Web 攻击。
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # 防止点击劫持
        response.headers["X-Frame-Options"] = "DENY"

        # 防止 MIME 类型嗅探
        response.headers["X-Content-Type-Options"] = "nosniff"

        # XSS 保护（虽然现代浏览器已废弃，但仍作为防御层）
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # 严格传输安全（生产环境启用）
        # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # 内容安全策略（按需调整）
        response.headers["Content-Security-Policy"] = "default-src 'self'"

        # 防止信息泄露
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        return response
```

### 8.3 请求体大小限制

在 `app/main.py` 中配置：

```python
from fastapi import FastAPI

app = FastAPI(
    # ...
)

# 请求体大小限制：10 MB
# FastAPI 本身不限制请求体大小，需要通过中间件或 uvicorn 配置
# 方式一：在 uvicorn 启动时设置
# uvicorn app.main:app --limit-max-size 10485760

# 方式二：自定义中间件检查 Content-Length
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """限制请求体大小"""

    MAX_SIZE = 10 * 1024 * 1024  # 10 MB

    async def dispatch(self, request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_SIZE:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": "请求体过大，最大允许 10MB",
                    }
                },
            )
        return await call_next(request)
```

### 8.4 CORS 配置检查

```python
# app/core/config.py 新增

class Settings(BaseSettings):
    # ... 已有配置 ...

    # CORS — 生产环境应明确指定允许的域名
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # 安全配置
    rate_limit_enabled: bool = True
    max_request_body_size: int = 10 * 1024 * 1024  # 10 MB
```

```python
# app/middleware/__init__.py 更新

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.middleware.rate_limiter import RateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware


def setup_middleware(app: FastAPI) -> None:
    """统一配置所有中间件"""

    # 注意中间件执行顺序（后添加的先执行）：
    # 请求 → SecurityHeaders → RateLimit → RequestLog → CORS → 路由处理

    # 1. CORS（最先添加，最后执行）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"],
        max_age=600,  # 预检请求缓存 10 分钟
    )

    # 2. 请求日志
    app.add_middleware(RequestLogMiddleware)

    # 3. Rate Limiting
    if settings.rate_limit_enabled:
        app.add_middleware(RateLimitMiddleware)

    # 4. 安全响应头（最后添加，最先执行）
    app.add_middleware(SecurityHeadersMiddleware)

    # 5. 请求体大小限制
    app.add_middleware(MaxBodySizeMiddleware)
```

### 8.5 安全加固清单

| 项目 | 状态 | 说明 |
|------|------|------|
| CORS 白名单 | ✅ | 生产环境从配置读取，不使用 `*` |
| Rate Limiting | ✅ | 分级别限流（认证/发布/默认/外部调用） |
| 请求体大小限制 | ✅ | 10MB 上限 |
| XSS 防护 | ✅ | 安全响应头 + FastAPI 自动转义 JSON |
| CSRF 防护 | ✅ | API 模式无需 CSRF（前端使用 JWT Token，不使用 Cookie） |
| SQL 注入 | ✅ | SQLAlchemy ORM 参数化查询 |
| API Key 安全 | ✅ | Redis 缓存使用哈希 Key，不存明文 |
| 安全响应头 | ✅ | X-Frame-Options, X-Content-Type-Options 等 |
| 敏感信息脱敏 | ✅ | API Key 列表接口脱敏显示 |
| 输入校验 | ✅ | Pydantic Schema 严格校验 |

---

## 9. 缓存策略

### 9.1 Redis 缓存键设计

| 缓存键 | 数据内容 | TTL | 失效条件 |
|--------|---------|-----|---------|
| `dashboard:stats:{user_id}` | Dashboard 统计概览 | 60s | TTL 过期 / 工作流/Agent/执行记录变更 |
| `dashboard:token_usage:{user_id}:{days}` | Token 趋势 | 60s | TTL 过期 / model_usages 变更 |
| `api_key:{sha256(api_key)[:32]}` | API Key → Workflow ID 映射 | 300s | 取消发布 / 重置 Key / 停用 |
| `search:{user_id}:{query_hash}` | 搜索结果 | 30s | TTL 过期 |

### 9.2 缓存失效策略

```python
# app/services/cache_invalidator.py

from app.core.redis import get_redis


class CacheInvalidator:
    """缓存失效管理器"""

    @staticmethod
    async def invalidate_dashboard(user_id: str):
        """失效 Dashboard 相关缓存"""
        redis = get_redis()
        # 删除统计缓存
        await redis.delete(f"dashboard:stats:{user_id}")
        # 删除所有 token_usage 缓存（使用 pattern）
        cursor = 0
        while True:
            cursor, keys = await redis.scan(
                cursor, match=f"dashboard:token_usage:{user_id}:*", count=100
            )
            if keys:
                await redis.delete(*keys)
            if cursor == 0:
                break

    @staticmethod
    async def invalidate_api_key(api_key: str):
        """失效 API Key 缓存"""
        from app.core.api_key_auth import hash_api_key
        redis = get_redis()
        cache_key = f"api_key:{hash_api_key(api_key)}"
        await redis.delete(cache_key)

    @staticmethod
    async def invalidate_search(user_id: str):
        """失效搜索缓存"""
        redis = get_redis()
        cursor = 0
        while True:
            cursor, keys = await redis.scan(
                cursor, match=f"search:{user_id}:*", count=100
            )
            if keys:
                await redis.delete(*keys)
            if cursor == 0:
                break
```

**触发失效的时机**：

| 操作 | 需要失效的缓存 |
|------|---------------|
| 创建/删除/更新工作流 | `dashboard:stats:*` |
| 执行工作流 | `dashboard:stats:*` |
| 创建/删除 Agent | `dashboard:stats:*` |
| 创建/删除知识库 | `dashboard:stats:*` |
| 发布/取消/重置 API Key | `api_key:*` |
| 停用/启用 API | `api_key:*` |

---

## 10. Service 层汇总

### 10.1 文件结构

```
app/services/
├── dashboard_service.py         # Dashboard 统计
├── publish_api_service.py       # API 发布管理
├── search_service.py            # 全局搜索
├── external_execution.py        # 外部 API 执行
├── rate_limit_service.py        # 外部调用限流
└── cache_invalidator.py         # 缓存失效管理
```

### 10.2 Service 依赖关系

```
DashboardService
  ├── 依赖: db (AsyncSession), redis
  ├── 查询: Workflow, Agent, KnowledgeBase, Execution, ModelUsage
  └── 输出: 统计数据

PublishApiService
  ├── 依赖: db, redis
  ├── 查询: Workflow
  ├── 调用: generate_api_key(), mask_api_key(), hash_api_key()
  └── 输出: API 发布信息

SearchService
  ├── 依赖: db
  ├── 查询: Workflow, Agent, KnowledgeBase, Template
  └── 输出: 分组搜索结果

ExternalExecutionService
  ├── 依赖: db, redis
  ├── 查询: Workflow, Execution
  ├── 调用: WorkflowExecutor（Phase 5）
  └── 输出: 执行结果

RateLimitService
  ├── 依赖: redis
  └── 输出: 限流判断结果

CacheInvalidator
  ├── 依赖: redis
  └── 输出: 缓存失效操作
```

---

## 11. 错误码汇总

### 11.1 Phase 7 新增错误码

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 400 | `EMPTY_WORKFLOW` | 工作流画布为空，无法发布 |
| 400 | `NOT_PUBLISHED` | 工作流未发布为 API |
| 400 | `MISSING_INPUT` | 外部调用缺少必填输入参数 |
| 401 | `API_KEY_MISSING` | 外部调用缺少 API Key |
| 401 | `INVALID_API_KEY` | 无效的 API Key |
| 403 | `API_DISABLED` | API 已被停用 |
| 408 | `EXECUTION_TIMEOUT` | 工作流执行超时 |
| 413 | `PAYLOAD_TOO_LARGE` | 请求体过大 |
| 429 | `RATE_LIMITED` | 请求频率超限 |
| 500 | `EXECUTION_FAILED` | 外部调用执行失败 |

### 11.2 与 Phase 0-6 错误码的关系

Phase 7 完全复用 Phase 0 定义的错误响应格式和基础异常类：

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "描述信息",
    "details": []
  }
}
```

Phase 7 不引入新的异常基类，所有新增错误均通过 `AppException` 抛出。

---

## 12. 与 Phase 0-6 的衔接

### 12.1 依赖 Phase 0

| Phase 0 资源 | Phase 7 使用方式 |
|-------------|-----------------|
| `Base`, `UUIDPrimaryKeyMixin`, `TimestampMixin` | 所有新模型继承 |
| `Workflow` 模型 | 新增 API 发布统计字段 |
| `Execution` 模型 | 新增 `source`, `api_caller_workflow_id` 字段 |
| `ModelUsage` 模型 | Token 趋势查询 |
| `Agent` 模型 | Dashboard 统计 |
| `KnowledgeBase` 模型 | Dashboard 统计 |
| `Template` 模型 | 全局搜索 |
| `AppException` | 所有错误抛出 |
| Redis 连接 | 缓存 + 限流 |
| 数据库连接 | 所有查询 |

### 12.2 依赖 Phase 1

| Phase 1 资源 | Phase 7 使用方式 |
|-------------|-----------------|
| `get_current_user` 依赖 | Dashboard/发布管理/搜索的认证 |
| User 模型 | user_id 过滤 |

### 12.3 依赖 Phase 4

| Phase 4 资源 | Phase 7 使用方式 |
|-------------|-----------------|
| `Workflow.nodes_data` | 外部调用时解析 startNode 输入 |
| `Workflow.is_published_api` | API 发布状态 |
| `Workflow.published_api_key` | API Key 存储 |

### 12.4 依赖 Phase 5

| Phase 5 资源 | Phase 7 使用方式 |
|-------------|-----------------|
| `WorkflowExecutor` | 外部 API 调用时同步执行工作流 |
| 执行引擎 | 复用 Phase 5 的完整执行逻辑 |

### 12.5 依赖 Phase 6

| Phase 6 资源 | Phase 7 使用方式 |
|-------------|-----------------|
| `Template` 模型 | 全局搜索 |
| 执行记录 API | 复用 Dashboard 的最近执行查询 |

### 12.6 Alembic 迁移顺序

```bash
# Phase 7 迁移文件
alembic revision --autogenerate -m "phase7_execution_source_fields"
alembic revision --autogenerate -m "phase7_workflow_api_stats_fields"
alembic revision --autogenerate -m "phase7_performance_indexes"

# 执行迁移
alembic upgrade head
```

---

## 13. 测试用例

### 13.1 Dashboard 测试

```python
# tests/test_dashboard.py

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_stats_success(client: AsyncClient, auth_headers: dict):
    """测试获取统计概览"""
    response = await client.get("/api/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert "workflow_count" in data
    assert "agent_count" in data
    assert "knowledge_base_count" in data
    assert "execution_count_this_month" in data
    assert "success_rate_this_month" in data
    assert 0 <= data["success_rate_this_month"] <= 100


@pytest.mark.asyncio
async def test_get_stats_unauthorized(client: AsyncClient):
    """测试未登录访问统计"""
    response = await client.get("/api/dashboard/stats")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_token_usage(client: AsyncClient, auth_headers: dict):
    """测试 Token 趋势"""
    response = await client.get(
        "/api/dashboard/token-usage?days=7", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["items"]) == 7
    assert "total_tokens" in data
    assert "total_cost" in data


@pytest.mark.asyncio
async def test_get_token_usage_invalid_days(client: AsyncClient, auth_headers: dict):
    """测试无效天数参数"""
    response = await client.get(
        "/api/dashboard/token-usage?days=100", headers=auth_headers
    )
    assert response.status_code == 422  # Pydantic 校验失败


@pytest.mark.asyncio
async def test_recent_workflows(client: AsyncClient, auth_headers: dict):
    """测试最近工作流"""
    response = await client.get(
        "/api/dashboard/recent-workflows?limit=3", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) <= 3


@pytest.mark.asyncio
async def test_recent_executions(client: AsyncClient, auth_headers: dict):
    """测试最近执行记录"""
    response = await client.get(
        "/api/dashboard/recent-executions", headers=auth_headers
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_stats_caching(client: AsyncClient, auth_headers: dict):
    """测试 Dashboard 缓存：两次请求应返回相同数据"""
    resp1 = await client.get("/api/dashboard/stats", headers=auth_headers)
    resp2 = await client.get("/api/dashboard/stats", headers=auth_headers)
    assert resp1.json()["data"] == resp2.json()["data"]
```

### 13.2 API 发布测试

```python
# tests/test_publish_api.py

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_publish_workflow(client: AsyncClient, auth_headers: dict, workflow_id: str):
    """测试发布工作流为 API"""
    response = await client.post(
        f"/api/workflows/{workflow_id}/publish-api", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["api_key"].startswith("sk-")
    assert len(data["api_key"]) == 35  # sk- + 32 chars
    assert "/api/published/" in data["endpoint_url"]


@pytest.mark.asyncio
async def test_publish_empty_workflow(client: AsyncClient, auth_headers: dict, empty_workflow_id: str):
    """测试发布空工作流"""
    response = await client.post(
        f"/api/workflows/{empty_workflow_id}/publish-api", headers=auth_headers
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_WORKFLOW"


@pytest.mark.asyncio
async def test_publish_idempotent(client: AsyncClient, auth_headers: dict, published_workflow_id: str):
    """测试重复发布是幂等的"""
    resp1 = await client.post(
        f"/api/workflows/{published_workflow_id}/publish-api", headers=auth_headers
    )
    resp2 = await client.post(
        f"/api/workflows/{published_workflow_id}/publish-api", headers=auth_headers
    )
    assert resp1.json()["data"]["api_key"] == resp2.json()["data"]["api_key"]


@pytest.mark.asyncio
async def test_unpublish(client: AsyncClient, auth_headers: dict, published_workflow_id: str):
    """测试取消发布"""
    response = await client.delete(
        f"/api/workflows/{published_workflow_id}/publish-api", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["message"] == "已取消发布"


@pytest.mark.asyncio
async def test_reset_api_key(client: AsyncClient, auth_headers: dict, published_workflow_id: str):
    """测试重置 API Key"""
    resp1 = await client.post(
        f"/api/workflows/{published_workflow_id}/publish-api/reset-key",
        headers=auth_headers,
    )
    old_key = resp1.json()["data"]["api_key"]

    resp2 = await client.post(
        f"/api/workflows/{published_workflow_id}/publish-api/reset-key",
        headers=auth_headers,
    )
    new_key = resp2.json()["data"]["api_key"]

    assert old_key != new_key


@pytest.mark.asyncio
async def test_list_published_apis(client: AsyncClient, auth_headers: dict):
    """测试已发布 API 列表"""
    response = await client.get("/api/published-apis", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert "items" in data
    assert "total" in data
    for item in data["items"]:
        assert "..." in item["api_key_masked"]  # 脱敏


@pytest.mark.asyncio
async def test_toggle_api(client: AsyncClient, auth_headers: dict, published_workflow_id: str):
    """测试启用/停用 API"""
    # 停用
    response = await client.put(
        f"/api/published-apis/{published_workflow_id}/toggle",
        headers=auth_headers,
        json={"is_active": False},
    )
    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is False

    # 启用
    response = await client.put(
        f"/api/published-apis/{published_workflow_id}/toggle",
        headers=auth_headers,
        json={"is_active": True},
    )
    assert response.json()["data"]["is_active"] is True
```

### 13.3 外部 API 调用测试

```python
# tests/test_external_api.py

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_external_run_success(client: AsyncClient, published_api_key: str):
    """测试外部调用成功"""
    response = await client.post(
        f"/api/published/{published_api_key}/run",
        json={"input": {"user_query": "Hello"}},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "success"
    assert "execution_id" in data
    assert "output" in data


@pytest.mark.asyncio
async def test_external_run_missing_input(client: AsyncClient, published_api_key: str):
    """测试缺少必填输入"""
    response = await client.post(
        f"/api/published/{published_api_key}/run",
        json={"input": {}},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MISSING_INPUT"


@pytest.mark.asyncio
async def test_external_run_invalid_key(client: AsyncClient):
    """测试无效 API Key"""
    response = await client.post(
        "/api/published/sk-invalidkey1234567890abcdef/run",
        json={"input": {}},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_external_run_disabled_api(client: AsyncClient, disabled_api_key: str):
    """测试调用已停用的 API"""
    response = await client.post(
        f"/api/published/{disabled_api_key}/run",
        json={"input": {"user_query": "test"}},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "API_DISABLED"


@pytest.mark.asyncio
async def test_external_run_via_header(client: AsyncClient, published_api_key: str):
    """测试通过 X-API-Key Header 调用"""
    response = await client.post(
        f"/api/published/{published_api_key}/run",
        json={"input": {"user_query": "Hello"}},
        headers={"X-API-Key": published_api_key},
    )
    assert response.status_code == 200
```

### 13.4 全局搜索测试

```python
# tests/test_search.py

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_global_search_all(client: AsyncClient, auth_headers: dict):
    """测试全局搜索（不限类型）"""
    response = await client.get(
        "/api/search?q=代码", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "workflows" in data
    assert "agents" in data
    assert "knowledge_bases" in data
    assert "templates" in data


@pytest.mark.asyncio
async def test_global_search_by_type(client: AsyncClient, auth_headers: dict):
    """测试按类型搜索"""
    response = await client.get(
        "/api/search?q=代码&type=workflow", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["workflows"]) > 0
    # 其他类型应为空
    assert len(data["agents"]) == 0


@pytest.mark.asyncio
async def test_search_no_results(client: AsyncClient, auth_headers: dict):
    """测试无结果搜索"""
    response = await client.get(
        "/api/search?q=xyzxyznonexistent", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_search_max_per_type(client: AsyncClient, auth_headers: dict):
    """测试每种类型最多返回 5 条"""
    response = await client.get(
        "/api/search?q=a", headers=auth_headers
    )
    data = response.json()["data"]
    for key in ["workflows", "agents", "knowledge_bases", "templates"]:
        assert len(data[key]) <= 5
```

---

## 14. 给 Cursor 的额外说明

### 14.1 实现顺序建议

请按以下顺序实现，每步完成后运行测试确认通过：

1. **数据库迁移**：创建 `phase7_*` 迁移文件，执行 `alembic upgrade head`
2. **模型更新**：更新 `Execution` 和 `Workflow` 模型的新字段
3. **Schema 定义**：创建 `app/schemas/dashboard.py`, `publish_api.py`, `search.py`, `external_api.py`
4. **API Key 认证**：实现 `app/core/api_key_auth.py`
5. **Service 层**：按顺序实现 `DashboardService` → `PublishApiService` → `SearchService` → `ExternalExecutionService` → `RateLimitService` → `CacheInvalidator`
6. **路由层**：按顺序实现 `dashboard.py` → `published_apis.py` → `workflows.py`（新增 publish 路由）→ `external_api.py` → `search.py`
7. **中间件**：实现 `rate_limiter.py` → `security_headers.py` → 更新 `__init__.py`
8. **路由注册**：更新 `app/api/router.py`
9. **缓存失效集成**：在已有的 Service 中集成 `CacheInvalidator` 调用
10. **测试**：按测试文件顺序执行

### 14.2 关键注意事项

1. **外部 API 路由不需要 JWT 认证**：`/api/published/{api_key}/run` 使用 API Key 认证，中间件中不要对它做 JWT 校验。
2. **API Key 格式**：`sk-` 前缀 + 32 位十六进制，总共 35 字符。
3. **幂等发布**：重复调用 publish 接口应返回相同的 API Key，不报错。
4. **WorkflowExecutor 复用**：外部调用时复用 Phase 5 实现的 `WorkflowExecutor`，不重新实现执行逻辑。
5. **统计字段原子更新**：使用 SQLAlchemy 的 `update().values(count=Model.count + 1)` 而非先读后写，避免并发问题。
6. **pg_trgm 扩展**：迁移开头必须 `CREATE EXTENSION IF NOT EXISTS pg_trgm`。
7. **缓存一致性**：Dashboard 数据缓存 60 秒是可接受的最终一致性延迟，不需要强一致性。
8. **搜索性能**：pg_trgm GIN 索引在数据量 < 100 万条时性能足够，无需引入 Elasticsearch。
9. **外部调用超时**：使用 `asyncio.wait_for` 包装执行调用，超时后正常返回失败结果（不抛出异常）。
10. **执行记录来源**：外部调用的 `Execution.source` 必须设为 `"api"`，便于后续区分统计。

### 14.3 环境变量新增

```env
# ---- Phase 7: API 发布 ----
API_KEY_PREFIX=sk-
API_KEY_LENGTH=32
EXTERNAL_API_TIMEOUT_SECONDS=300

# ---- Phase 7: 限流 ----
RATE_LIMIT_PER_MINUTE_AUTH=10
RATE_LIMIT_PER_MINUTE_PUBLISH=5
RATE_LIMIT_PER_MINUTE_DEFAULT=120
RATE_LIMIT_PER_MINUTE_EXTERNAL=30
RATE_LIMIT_PER_DAY_EXTERNAL=1000

# ---- Phase 7: 缓存 ----
DASHBOARD_CACHE_TTL=60
API_KEY_CACHE_TTL=300
SEARCH_CACHE_TTL=30
```

### 14.4 依赖新增

```
# requirements.txt 新增（Phase 7）
# 无需额外依赖，全部使用 Phase 0 已有的依赖即可。
# pg_trgm 是 PostgreSQL 内置扩展，通过 SQL 启用。
```

### 14.5 与前端对接说明

| 前端页面 | 调用的 Phase 7 API | 备注 |
|---------|-------------------|------|
| Dashboard 首页 | `GET /api/dashboard/*` (4个接口) | 统计/趋势/最近工作流/最近执行 |
| 工作流编辑器 - 发布按钮 | `POST /api/workflows/:id/publish-api` | 弹出 API Key 和 Endpoint |
| 设置 - API 管理 | `GET /api/published-apis` + `PUT .../toggle` + `POST .../reset-key` | 列表/启停/重置 |
| 顶部导航 - 搜索框 | `GET /api/search?q=...` | 输入即搜索 |
| 工作流编辑器 - 取消发布 | `DELETE /api/workflows/:id/publish-api` | 确认弹窗后调用 |

---

## 15. 附录

### 15.1 完整 API 路由清单

```
# Dashboard（需 JWT）
GET    /api/dashboard/stats
GET    /api/dashboard/token-usage
GET    /api/dashboard/recent-workflows
GET    /api/dashboard/recent-executions

# 工作流发布（需 JWT）
POST   /api/workflows/:id/publish-api
DELETE /api/workflows/:id/publish-api
POST   /api/workflows/:id/publish-api/reset-key

# 已发布 API 管理（需 JWT）
GET    /api/published-apis
PUT    /api/published-apis/:workflow_id/toggle

# 外部调用（API Key 认证，无需 JWT）
POST   /api/published/{api_key}/run

# 全局搜索（需 JWT）
GET    /api/search
```

### 15.2 API Key 认证完整流程

```
外部系统                    后端服务                     Redis              PostgreSQL
  |                           |                           |                    |
  |-- POST /api/published/sk-xxx/run ------------------>  |                    |
  |   {input: {...}}           |                           |                    |
  |                           |-- GET api_key:{hash} ---->|                    |
  |                           |<-- workflow_id (cached) --|                    |
  |                           |                           |                    |
  |                           |-- SELECT workflow WHERE --|-------------------->|
  |                           |   id = {cached_wf_id}     |                    |
  |                           |   AND is_published_api    |                    |
  |                           |   AND api_is_active       |<-------------------|
  |                           |<-- workflow record -------|--------------------|
  |                           |                           |                    |
  |                           |-- [限流检查]              |                    |
  |                           |-- INCR rate_limit:{key} ->|                    |
  |                           |                           |                    |
  |                           |-- [执行工作流]            |                    |
  |                           |-- WorkflowExecutor.run    |                    |
  |                           |                           |                    |
  |                           |-- UPDATE workflow stats --|-------------------->|
  |                           |-- INSERT execution -------|-------------------->|
  |                           |                           |                    |
  |<-- {execution_id, output} |                           |                    |
```

### 15.3 Dashboard 查询优化说明

| 查询 | 优化手段 | 预期耗时 |
|------|---------|---------|
| 工作流/Agent/知识库 COUNT | 已有 user_id 索引 | < 5ms |
| 本月执行次数 | `ix_executions_user_month` 部分索引 | < 10ms |
| 本月成功率 | 同上，合并为一次查询 | < 10ms |
| Token 趋势 | `ix_model_usages_user_date` 索引 | < 20ms |
| 最近工作流 | `ix_workflows_user_updated` 索引 | < 5ms |
| 最近执行 | `ix_executions_user_started` 索引 | < 5ms |
| 全局搜索 | pg_trgm GIN 索引 | < 50ms |

所有 Dashboard 查询结果缓存 60 秒，进一步降低数据库压力。

---

> **Phase 7 文档结束**  
> 至此，「汤圆的代码助手」后端开发文档 Phase 0 ~ Phase 7 全部完成。  
> 按文档顺序实现，Cursor 应能直接生成可运行的完整后端代码。

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
