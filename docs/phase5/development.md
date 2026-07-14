---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 4263223131904378_0/project_7661866342080954651-files/Phase5/phase5_backend.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 4263223131904378#1784021192184
    ReservedCode2: ""
---
# 汤圆的代码助手 - Phase 5 后端开发文档：工作流执行引擎

> **目标读者**：Cursor / AI Coding Agent  
> **版本**：Phase 5 v1.0  
> **项目代号**：`tangyuan-backend`  
> **前置条件**：Phase 0（脚手架 + 数据库模型）+ Phase 1（用户系统）+ Phase 2（Agent + 工具 + 模型管理）+ Phase 3（知识库管理）+ Phase 4（工作流编辑器 + 单节点调试）已完成

---

## 1. 目标

在 Phase 0-4 基础上实现**完整的工作流执行引擎**，包括：

- **工作流执行引擎（核心）**：接收工作流定义，拓扑排序后按序执行每个节点，支持条件分支/并行执行/循环迭代
- **WebSocket 实时推送**：执行过程中实时推送节点状态、日志、审核请求
- **16 种节点类型的完整执行逻辑**：复用 Phase 4 的单节点调试执行器，扩展为完整工作流执行版本
- **执行记录与日志**：创建 Execution/ExecutionNode/Log 记录
- **审核节点暂停/恢复**：支持人工审核中断和恢复执行
- **执行中断**：支持取消正在执行的工作流
- **执行历史查询**：列表/详情/日志查询 API

Phase 5 完成后，用户应能：点击「运行」→ 实时观察每个节点执行状态 → 审核节点暂停等待人工操作 → 执行完成后查看完整记录。

---

## 2. 数据库变更

### 2.1 表结构确认（复用 Phase 0 定义）

Phase 5 复用 Phase 0 定义的 `Execution`、`ExecutionNode`、`Log` 三张表，无需新增表。

#### Execution 表（`executions`）

```python
# app/models/execution.py（Phase 0 定义，Phase 5 复用）

class Execution(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "executions"

    workflow_id: Mapped[uuid.UUID]        # 关联工作流
    version_number: Mapped[int]            # 执行的版本号
    status: Mapped[ExecutionStatus]        # pending | running | success | failed | paused | cancelled
    input_data: Mapped[Optional[dict]]     # 全局输入参数（JSONB）
    output_data: Mapped[Optional[dict]]    # 最终输出（JSONB）
    total_duration_ms: Mapped[Optional[int]]
    total_tokens: Mapped[Optional[int]]
    total_cost: Mapped[Optional[Decimal]]
    started_at: Mapped[datetime]
    finished_at: Mapped[Optional[datetime]]

    # Relationships
    workflow = relationship("Workflow", back_populates="executions")
    nodes = relationship("ExecutionNode", back_populates="execution", cascade="all, delete-orphan")
    logs = relationship("Log", back_populates="execution", cascade="all, delete-orphan")
```

#### ExecutionNode 表（`execution_nodes`）

```python
class ExecutionNode(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "execution_nodes"

    execution_id: Mapped[uuid.UUID]        # 关联执行记录
    node_id: Mapped[str]                   # 工作流中的节点 ID
    node_type: Mapped[str]                 # 节点类型
    status: Mapped[NodeStatus]             # pending | running | success | failed | skipped | paused
    input_data: Mapped[Optional[dict]]     # 节点输入（JSONB）
    output_data: Mapped[Optional[dict]]    # 节点输出（JSONB）
    duration_ms: Mapped[Optional[int]]
    tokens_used: Mapped[Optional[int]]
    error_message: Mapped[Optional[str]]
    started_at: Mapped[datetime]
    finished_at: Mapped[Optional[datetime]]

    # Relationships
    execution = relationship("Execution", back_populates="nodes")
```

#### Log 表（`logs`）

```python
class Log(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "logs"

    execution_id: Mapped[uuid.UUID]        # 关联执行记录
    node_id: Mapped[Optional[str]]         # 关联节点（可选）
    level: Mapped[LogLevel]                # info | warn | error
    message: Mapped[str]                   # 日志内容
    timestamp: Mapped[datetime]

    # Relationships
    execution = relationship("Execution", back_populates="logs")
```

### 2.2 新增索引

```sql
-- 执行历史查询优化
CREATE INDEX ix_executions_workflow_status ON executions (workflow_id, status);
CREATE INDEX ix_executions_started_at ON executions (started_at DESC);

-- 日志查询优化
CREATE INDEX ix_logs_execution_node ON logs (execution_id, node_id);
CREATE INDEX ix_logs_level ON logs (level);
```

### 2.3 新增 Pydantic Schema `app/schemas/execution.py`

```python
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, Any
from pydantic import BaseModel, Field


# ==================== 启动执行 ====================

class WorkflowRunRequest(BaseModel):
    """启动工作流执行的请求"""
    input_data: dict[str, Any] = Field(default_factory=dict)
    # 全局输入参数，key 为开始节点定义的变量名


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
    nodes: list["ExecutionNodeDetail"] = []

    model_config = {"from_attributes": True}


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


class LogListResponse(BaseModel):
    items: list["LogDetailResponse"]
    total: int
    page: int
    page_size: int
    has_next: bool


class LogDetailResponse(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    node_id: Optional[str] = None
    level: str
    message: str
    timestamp: datetime

    model_config = {"from_attributes": True}
```

---

## 3. 执行引擎核心架构

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        WorkflowExecutor (主控制器)                       │
│                                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐ │
│  │ 拓扑排序器   │  │ 变量解析引擎  │  │ 执行上下文   │  │ WebSocket    │ │
│  │ TopoSorter  │  │ VarResolver  │  │ ExecContext  │  │ Broadcaster  │ │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
│         │                │                  │                  │         │
│  ┌──────▼──────────────────────────────────────────────────────▼───────┐ │
│  │                     NodeExecutorDispatcher                          │ │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐  │ │
│  │  │Start │ │Agent │ │ KB   │ │Code  │ │HTTP  │ │Cond  │ │Para. │  │ │
│  │  │Exec  │ │Exec  │ │Exec  │ │Exec  │ │Exec  │ │Exec  │ │Exec  │  │ │
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘  │ │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐  │ │
│  │  │Loop  │ │Review│ │Test  │ │Delay │ │Tmpl  │ │Aggr. │ │Clsfy │  │ │
│  │  │Exec  │ │Exec  │ │Exec  │ │Exec  │ │Exec  │ │Exec  │ │Exec  │  │ │
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘  │ │
│  │  ┌──────┐ ┌──────┐                                                │ │
│  │  │Extr. │ │End   │                                                │ │
│  │  │Exec  │ │Exec  │                                                │ │
│  │  └──────┘ └──────┘                                                │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 文件结构

```
app/
├── services/
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── executor.py              # WorkflowExecutor 主类
│   │   ├── context.py               # ExecutionContext 上下文管理
│   │   ├── topo_sorter.py           # 拓扑排序算法
│   │   ├── variable_resolver.py     # 变量解析引擎
│   │   ├── ws_broadcaster.py        # WebSocket 广播器
│   │   ├── cancellation.py          # 执行取消管理
│   │   └── review_manager.py        # 审核暂停/恢复管理
│   ├── node_executors/              # Phase 4 已有，Phase 5 扩展
│   │   ├── base.py                  # BaseNodeExecutor 基类（扩展）
│   │   ├── registry.py              # 执行器注册表（扩展）
│   │   ├── start_executor.py        # 开始节点（新增）
│   │   ├── end_executor.py          # 结束节点（新增）
│   │   ├── agent_executor.py        # Agent 节点（扩展 Phase 4）
│   │   ├── knowledge_executor.py    # 知识检索节点（扩展 Phase 4）
│   │   ├── condition_executor.py    # 条件分支节点（扩展 Phase 4）
│   │   ├── parallel_executor.py     # 并行执行节点（重写）
│   │   ├── loop_executor.py         # 循环迭代节点（重写）
│   │   ├── review_executor.py       # 审核节点（新增）
│   │   ├── test_executor.py         # 测试节点（新增）
│   │   ├── delay_executor.py        # 延时等待节点（扩展 Phase 4）
│   │   ├── code_executor.py         # 代码执行节点（扩展 Phase 4）
│   │   ├── http_executor.py         # HTTP 请求节点（扩展 Phase 4）
│   │   ├── template_executor.py     # 模板转换节点（扩展 Phase 4）
│   │   ├── aggregate_executor.py    # 变量聚合节点（扩展 Phase 4）
│   │   ├── classify_executor.py     # 问题分类节点（扩展 Phase 4）
│   │   └── extract_executor.py      # 参数提取节点（扩展 Phase 4）
│   ├── execution_service.py         # 执行管理 Service
│   └── log_service.py               # 日志 Service
├── api/v1/
│   ├── executions.py                # 执行记录路由
│   └── ws.py                        # WebSocket 路由
```

### 3.3 WorkflowExecutor 主类

```python
# app/services/execution/executor.py

import asyncio
import time
import uuid
import structlog
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import Execution, ExecutionNode, Log
from app.models.enums import ExecutionStatus, NodeStatus, LogLevel
from app.services.execution.context import ExecutionContext
from app.services.execution.topo_sorter import TopoSorter
from app.services.execution.variable_resolver import VariableResolver
from app.services.execution.ws_broadcaster import WSBroadcaster
from app.services.execution.cancellation import CancellationManager
from app.services.execution.review_manager import ReviewManager
from app.services.node_executors.registry import NodeExecutorRegistry

logger = structlog.get_logger()


class WorkflowExecutor:
    """
    工作流执行引擎主类。
    
    职责：
    1. 解析工作流定义（nodes_data + edges_data）
    2. 拓扑排序确定执行顺序
    3. 按顺序执行每个节点
    4. 处理条件分支/并行执行/循环迭代的路由逻辑
    5. 管理变量传递和解析
    6. 通过 WebSocket 广播执行状态
    7. 记录执行日志和结果
    """

    def __init__(
        self,
        db: AsyncSession,
        redis,
        broadcaster: WSBroadcaster,
        cancellation_mgr: CancellationManager,
        review_mgr: ReviewManager,
    ):
        self.db = db
        self.redis = redis
        self.broadcaster = broadcaster
        self.cancellation_mgr = cancellation_mgr
        self.review_mgr = review_mgr

    async def execute(
        self,
        execution: Execution,
        nodes_data: list[dict],
        edges_data: list[dict],
        input_data: dict[str, Any],
        user_id: uuid.UUID,
    ) -> None:
        """
        执行工作流主入口。
        
        伪代码流程：
        1. 初始化执行上下文
        2. 拓扑排序
        3. 遍历排序后的节点，逐个执行
        4. 处理条件分支（跳过不匹配的分支路径）
        5. 处理并行执行（asyncio.gather）
        6. 处理循环迭代（遍历数组）
        7. 处理审核暂停（等待信号恢复）
        8. 检查取消标志
        9. 更新执行记录
        """
        start_time = time.time()
        total_tokens = 0

        # 1. 初始化执行上下文
        ctx = ExecutionContext(
            execution_id=execution.id,
            workflow_id=execution.workflow_id,
            user_id=user_id,
            db_session=self.db,
            redis_client=self.redis,
            broadcaster=self.broadcaster,
            cancellation_mgr=self.cancellation_mgr,
            review_mgr=self.review_mgr,
        )

        # 将全局输入参数存入上下文
        ctx.set_global_input(input_data)

        # 2. 拓扑排序
        sorter = TopoSorter(nodes_data, edges_data)
        execution_order = sorter.sort()
        # execution_order 返回: list[dict]，每个元素包含：
        # {
        #     "node": {...},           # 原始节点数据
        #     "group": str | None,     # 所属组（并行/循环）
        #     "depth": int,            # 拓扑深度
        #     "skip": bool,            # 是否跳过（条件分支未命中）
        # }

        # 3. 更新执行状态为 running
        execution.status = ExecutionStatus.running
        await self.db.flush()

        # 广播执行开始
        await self.broadcaster.broadcast(execution.id, {
            "type": "execution_status",
            "status": "running",
            "total_nodes": len(execution_order),
        })

        try:
            # 4. 按拓扑顺序执行节点
            for step in execution_order:
                node = step["node"]
                node_id = node["id"]
                node_type = node["type"]

                # 4a. 检查取消标志
                if await self.cancellation_mgr.is_cancelled(execution.id):
                    await self._handle_cancellation(execution, ctx)
                    return

                # 4b. 跳过被条件分支排除的节点
                if step.get("skip", False):
                    await self._skip_node(execution, node_id, node_type, ctx)
                    continue

                # 4c. 执行节点
                result = await self._execute_node(
                    execution=execution,
                    node=node,
                    ctx=ctx,
                )

                # 4d. 累计 Token
                if result.get("tokens_used"):
                    total_tokens += result["tokens_used"]

                # 4e. 处理条件分支结果
                if node_type == "conditionNode":
                    matched_branch = result.get("output", {}).get("matched_branch")
                    sorter.mark_branch_result(node_id, matched_branch, edges_data)
                    # 更新后续节点的 skip 状态
                    for future_step in execution_order:
                        if sorter.should_skip(future_step["node"]["id"]):
                            future_step["skip"] = True

            # 5. 执行成功完成
            execution.status = ExecutionStatus.success
            execution.output_data = ctx.get_end_outputs()
            execution.total_duration_ms = int((time.time() - start_time) * 1000)
            execution.total_tokens = total_tokens
            execution.finished_at = datetime.now(timezone.utc)

            await self.broadcaster.broadcast(execution.id, {
                "type": "execution_status",
                "status": "success",
                "total_duration_ms": execution.total_duration_ms,
                "total_tokens": total_tokens,
                "output": execution.output_data,
            })

        except ReviewPausedException as e:
            # 审核暂停
            execution.status = ExecutionStatus.paused
            await self.db.flush()

        except Exception as e:
            # 执行失败
            execution.status = ExecutionStatus.failed
            execution.total_duration_ms = int((time.time() - start_time) * 1000)
            execution.total_tokens = total_tokens
            execution.finished_at = datetime.now(timezone.utc)

            await self._log_error(execution.id, str(e))
            await self.broadcaster.broadcast(execution.id, {
                "type": "execution_status",
                "status": "failed",
                "total_duration_ms": execution.total_duration_ms,
                "error": str(e),
            })
            logger.error("execution_failed", execution_id=str(execution.id), error=str(e))

        finally:
            await self.db.flush()

    async def _execute_node(
        self,
        execution: Execution,
        node: dict,
        ctx: ExecutionContext,
    ) -> dict:
        """
        执行单个节点。
        
        步骤：
        1. 创建 ExecutionNode 记录（status=running）
        2. 解析输入变量
        3. 调用对应执行器
        4. 更新 ExecutionNode 记录
        5. 将输出存入上下文
        6. 广播状态变更
        7. 记录日志
        """
        node_id = node["id"]
        node_type = node["type"]
        node_data = node.get("data", {})
        node_start = time.time()

        # 1. 创建 ExecutionNode 记录
        exec_node = ExecutionNode(
            id=uuid.uuid4(),
            execution_id=execution.id,
            node_id=node_id,
            node_type=node_type,
            status=NodeStatus.running,
            input_data=ctx.get_node_inputs(node_id, node_data),
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(exec_node)
        await self.db.flush()

        # 2. 广播节点开始
        await self.broadcaster.broadcast(execution.id, {
            "type": "node_status_change",
            "node_id": node_id,
            "status": "running",
            "started_at": exec_node.started_at.isoformat(),
        })

        await self._log_info(
            execution.id, node_id,
            f"开始执行节点: {node_data.get('label', node_id)} ({node_type})"
        )

        try:
            # 3. 解析输入变量
            resolved_inputs = ctx.resolve_all_variables(node_data)

            # 4. 获取执行器并执行
            executor = NodeExecutorRegistry.get_executor(node_type)
            
            # 特殊处理：并行执行节点
            if node_type == "parallelNode":
                result = await self._execute_parallel(
                    execution, node, ctx, executor
                )
            # 特殊处理：循环节点
            elif node_type == "loopNode":
                result = await self._execute_loop(
                    execution, node, ctx, executor
                )
            # 特殊处理：审核节点
            elif node_type == "reviewNode":
                result = await self._execute_review(
                    execution, node, ctx, executor
                )
            else:
                # 常规执行
                exec_result = await executor.execute(
                    config=node_data,
                    input_variables=resolved_inputs,
                    context=ctx,
                )
                result = {
                    "output": exec_result.output,
                    "tokens_used": exec_result.tokens_used,
                    "error": exec_result.error,
                }

            duration_ms = int((time.time() - node_start) * 1000)

            # 5. 检查执行结果
            if result.get("error"):
                # 节点执行失败
                exec_node.status = NodeStatus.failed
                exec_node.error_message = result["error"]
                exec_node.duration_ms = duration_ms
                exec_node.finished_at = datetime.now(timezone.utc)

                await self.broadcaster.broadcast(execution.id, {
                    "type": "node_status_change",
                    "node_id": node_id,
                    "status": "failed",
                    "error": result["error"],
                    "duration_ms": duration_ms,
                    "finished_at": exec_node.finished_at.isoformat(),
                })
                await self.broadcaster.broadcast(execution.id, {
                    "type": "error",
                    "node_id": node_id,
                    "error_message": result["error"],
                })
                await self._log_error(execution.id, node_id, result["error"])

                # 根据节点配置决定是否终止执行
                if node_data.get("on_failure", "abort") == "abort":
                    raise ExecutionNodeError(
                        f"节点 {node_id} 执行失败: {result['error']}",
                        node_id=node_id,
                    )
            else:
                # 节点执行成功
                exec_node.status = NodeStatus.success
                exec_node.output_data = result.get("output", {})
                exec_node.duration_ms = duration_ms
                exec_node.tokens_used = result.get("tokens_used")
                exec_node.finished_at = datetime.now(timezone.utc)

                # 6. 将输出存入上下文
                ctx.set_node_output(node_id, result.get("output", {}))

                await self.broadcaster.broadcast(execution.id, {
                    "type": "node_status_change",
                    "node_id": node_id,
                    "status": "success",
                    "output": result.get("output"),
                    "duration_ms": duration_ms,
                    "tokens_used": result.get("tokens_used"),
                    "finished_at": exec_node.finished_at.isoformat(),
                })
                await self._log_info(
                    execution.id, node_id,
                    f"节点执行成功: {node_data.get('label', node_id)} "
                    f"(耗时 {duration_ms}ms, Token: {result.get('tokens_used', 0)})"
                )

            await self.db.flush()
            return result

        except ReviewPausedException:
            # 审核暂停：更新节点状态为 paused
            exec_node.status = NodeStatus.paused
            exec_node.finished_at = None
            await self.db.flush()

            await self.broadcaster.broadcast(execution.id, {
                "type": "review_request",
                "node_id": node_id,
                "input_data": exec_node.input_data,
            })
            await self.broadcaster.broadcast(execution.id, {
                "type": "node_status_change",
                "node_id": node_id,
                "status": "paused",
            })

            raise  # 向上抛出，暂停整个工作流

        except ExecutionNodeError:
            raise  # 向上传播
        except Exception as e:
            # 未预期的错误
            duration_ms = int((time.time() - node_start) * 1000)
            exec_node.status = NodeStatus.failed
            exec_node.error_message = str(e)
            exec_node.duration_ms = duration_ms
            exec_node.finished_at = datetime.now(timezone.utc)
            await self.db.flush()

            await self.broadcaster.broadcast(execution.id, {
                "type": "node_status_change",
                "node_id": node_id,
                "status": "failed",
                "error": str(e),
                "duration_ms": duration_ms,
                "finished_at": exec_node.finished_at.isoformat(),
            })
            await self._log_error(execution.id, node_id, str(e))
            raise ExecutionNodeError(str(e), node_id=node_id)

    async def _execute_parallel(
        self,
        execution: Execution,
        node: dict,
        ctx: ExecutionContext,
        executor,
    ) -> dict:
        """
        并行执行节点：并发执行多个分支，等待全部完成。
        
        逻辑：
        1. 获取并行分支配置
        2. 对每个分支，找到分支内的所有节点
        3. 使用 asyncio.gather 并发执行所有分支
        4. 合并所有分支的输出
        """
        node_data = node.get("data", {})
        branches = node_data.get("branches", [])
        wait_mode = node_data.get("wait_mode", "all")

        branch_tasks = []
        for branch in branches:
            branch_id = branch["id"]
            branch_nodes = ctx.get_branch_nodes(node["id"], branch_id)
            branch_tasks.append(
                self._execute_branch(execution, branch_id, branch_nodes, ctx)
            )

        if wait_mode == "all":
            results = await asyncio.gather(*branch_tasks, return_exceptions=True)
        else:  # "any"
            done, pending = await asyncio.wait(
                [asyncio.create_task(t) for t in branch_tasks],
                return_when=asyncio.FIRST_COMPLETED,
            )
            results = [t.result() for t in done]
            for t in pending:
                t.cancel()

        # 合并分支输出
        merged_output = {}
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                merged_output[f"branch_{i}_error"] = str(result)
            else:
                merged_output[f"branch_{i}"] = result

        return {
            "output": {"parallel_result": merged_output},
            "tokens_used": None,
            "error": None,
        }

    async def _execute_branch(
        self,
        execution: Execution,
        branch_id: str,
        branch_nodes: list[dict],
        ctx: ExecutionContext,
    ) -> dict:
        """执行并行分支内的节点序列"""
        branch_output = {}
        for node in branch_nodes:
            result = await self._execute_node(execution, node, ctx)
            if result.get("output"):
                branch_output.update(result["output"])
        return branch_output

    async def _execute_loop(
        self,
        execution: Execution,
        node: dict,
        ctx: ExecutionContext,
        executor,
    ) -> dict:
        """
        循环迭代节点：遍历数组，对每个元素执行子流程。
        
        逻辑：
        1. 解析 loop_variable 获取要遍历的数组
        2. 获取循环体内的子节点
        3. 对每个元素：设置 item 和 index 变量，执行子流程
        4. 收集所有迭代结果
        """
        node_data = node.get("data", {})
        loop_var_ref = node_data.get("loop_variable", "")
        item_name = node_data.get("item_name", "item")
        index_name = node_data.get("index_name", "index")

        # 解析循环变量
        resolver = VariableResolver()
        loop_array = resolver.resolve(loop_var_ref, ctx.variables)

        if not isinstance(loop_array, list):
            return {
                "output": {"error": "Loop variable is not an array"},
                "error": "Loop variable is not an array",
            }

        # 获取循环体子节点
        child_nodes = ctx.get_loop_child_nodes(node["id"])

        # 遍历执行
        all_results = []
        for idx, item in enumerate(loop_array):
            # 检查取消标志
            if await self.cancellation_mgr.is_cancelled(execution.id):
                break

            # 设置迭代变量
            ctx.set_iteration_variables(item_name, item, index_name, idx)

            # 执行子流程
            iteration_output = {}
            for child_node in child_nodes:
                result = await self._execute_node(execution, child_node, ctx)
                if result.get("output"):
                    iteration_output.update(result["output"])

            all_results.append({
                "index": idx,
                "item": item,
                "output": iteration_output,
            })

            # 清除迭代变量
            ctx.clear_iteration_variables()

        return {
            "output": {
                "loop_results": all_results,
                "total_iterations": len(all_results),
            },
            "tokens_used": None,
            "error": None,
        }

    async def _execute_review(
        self,
        execution: Execution,
        node: dict,
        ctx: ExecutionContext,
        executor,
    ) -> dict:
        """
        审核节点：暂停执行，等待人工审核。
        
        逻辑：
        1. 广播审核请求到前端
        2. 抛出 ReviewPausedException 暂停工作流
        3. 等待 ReviewManager 的信号
        4. 收到审核结果后恢复执行
        """
        node_data = node.get("data", {})
        node_id = node["id"]

        # 准备审核数据
        review_input = ctx.get_node_inputs(node_id, node_data)

        # 广播审核请求
        await self.broadcaster.broadcast(execution.id, {
            "type": "review_request",
            "node_id": node_id,
            "input_data": review_input,
        })

        # 等待审核结果（通过 Redis Pub/Sub 或 asyncio.Event）
        review_result = await self.review_mgr.wait_for_review(
            execution_id=execution.id,
            node_id=node_id,
            timeout=node_data.get("timeout_seconds", 3600),
        )

        # 处理审核结果
        action = review_result.get("action")
        if action == "approve":
            return {
                "output": {
                    "review_action": "approved",
                    "review_comment": review_result.get("comment"),
                },
                "tokens_used": None,
                "error": None,
            }
        elif action == "reject":
            return {
                "output": {
                    "review_action": "rejected",
                    "review_comment": review_result.get("comment"),
                },
                "tokens_used": None,
                "error": f"审核被拒绝: {review_result.get('comment', '无备注')}",
            }
        elif action == "modify":
            modified_data = review_result.get("modified_data", {})
            return {
                "output": modified_data,
                "tokens_used": None,
                "error": None,
            }
        else:
            return {
                "output": {"review_action": "timeout"},
                "tokens_used": None,
                "error": "审核超时",
            }

    async def _skip_node(
        self,
        execution: Execution,
        node_id: str,
        node_type: str,
        ctx: ExecutionContext,
    ):
        """跳过被条件分支排除的节点"""
        exec_node = ExecutionNode(
            id=uuid.uuid4(),
            execution_id=execution.id,
            node_id=node_id,
            node_type=node_type,
            status=NodeStatus.skipped,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            duration_ms=0,
        )
        self.db.add(exec_node)
        await self.db.flush()

        await self.broadcaster.broadcast(execution.id, {
            "type": "node_status_change",
            "node_id": node_id,
            "status": "skipped",
        })

    async def _handle_cancellation(self, execution: Execution, ctx: ExecutionContext):
        """处理执行取消"""
        execution.status = ExecutionStatus.cancelled
        execution.finished_at = datetime.now(timezone.utc)
        await self.db.flush()

        await self.broadcaster.broadcast(execution.id, {
            "type": "execution_status",
            "status": "cancelled",
        })
        await self._log_info(execution.id, None, "执行已被用户取消")

    async def _log_info(self, execution_id, node_id, message):
        await self._create_log(execution_id, node_id, LogLevel.info, message)

    async def _log_error(self, execution_id, node_id, message):
        await self._create_log(execution_id, node_id, LogLevel.error, message)

    async def _create_log(self, execution_id, node_id, level, message):
        log = Log(
            id=uuid.uuid4(),
            execution_id=execution_id,
            node_id=node_id,
            level=level,
            message=message,
        )
        self.db.add(log)
        await self.db.flush()

        # 同时通过 WebSocket 推送
        await self.broadcaster.broadcast(execution_id, {
            "type": "log",
            "level": level.value,
            "message": message,
            "node_id": node_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


class ReviewPausedException(Exception):
    """审核暂停异常，用于中断工作流执行"""
    pass


class ExecutionNodeError(Exception):
    """节点执行错误"""
    def __init__(self, message: str, node_id: str = None):
        super().__init__(message)
        self.node_id = node_id
```

### 3.4 ExecutionContext（上下文管理）

```python
# app/services/execution/context.py

import re
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession


class ExecutionContext:
    """
    工作流执行上下文。
    
    管理：
    - 全局输入变量
    - 每个节点的输出变量
    - 迭代变量（循环节点）
    - 环境变量缓存
    - 执行路径信息（并行分支、循环体子节点）
    """

    def __init__(
        self,
        execution_id,
        workflow_id,
        user_id,
        db_session: AsyncSession,
        redis_client,
        broadcaster,
        cancellation_mgr,
        review_mgr,
    ):
        self.execution_id = execution_id
        self.workflow_id = workflow_id
        self.user_id = user_id
        self.db_session = db_session
        self.redis_client = redis_client
        self.broadcaster = broadcaster
        self.cancellation_mgr = cancellation_mgr
        self.review_mgr = review_mgr

        # 变量存储
        self._global_input: dict[str, Any] = {}
        self._node_outputs: dict[str, dict[str, Any]] = {}
        self._iteration_vars: dict[str, Any] = {}
        self._env_cache: dict[str, str] = {}

        # 图结构信息
        self._nodes_data: list[dict] = []
        self._edges_data: list[dict] = []
        self._node_map: dict[str, dict] = {}

    def set_graph(self, nodes_data: list[dict], edges_data: list[dict]):
        """设置工作流图结构"""
        self._nodes_data = nodes_data
        self._edges_data = edges_data
        self._node_map = {n["id"]: n for n in nodes_data}

    def set_global_input(self, input_data: dict[str, Any]):
        """设置全局输入参数"""
        self._global_input = input_data

    def set_node_output(self, node_id: str, output: dict[str, Any]):
        """存储节点输出"""
        self._node_outputs[node_id] = output or {}

    def get_node_output(self, node_id: str) -> dict[str, Any]:
        """获取节点输出"""
        return self._node_outputs.get(node_id, {})

    def set_iteration_variables(self, item_name: str, item: Any, index_name: str, index: int):
        """设置循环迭代变量"""
        self._iteration_vars[item_name] = item
        self._iteration_vars[index_name] = index

    def clear_iteration_variables(self):
        """清除循环迭代变量"""
        self._iteration_vars.clear()

    @property
    def variables(self) -> dict[str, Any]:
        """
        获取所有可用变量的扁平化视图。
        
        变量查找优先级：
        1. 迭代变量（循环体内部）
        2. 节点输出（node_id.var_name）
        3. 全局输入
        4. 环境变量（env.VAR_NAME）
        """
        all_vars = {}

        # 全局输入（以 input. 前缀）
        for key, value in self._global_input.items():
            all_vars[f"input.{key}"] = value

        # 节点输出（以 node_id. 前缀）
        for node_id, outputs in self._node_outputs.items():
            for var_name, value in outputs.items():
                all_vars[f"{node_id}.{var_name}"] = value

        # 迭代变量
        all_vars.update(self._iteration_vars)

        return all_vars

    def resolve_variable(self, ref: str) -> Any:
        """
        解析单个变量引用。
        
        支持格式：
        - ${node_id.var_name} → 节点输出
        - ${input.param_name} → 全局输入
        - ${env.VAR_NAME} → 环境变量
        - ${item} → 迭代变量（循环体内）
        """
        # 去掉 ${ 和 }
        if ref.startswith("${") and ref.endswith("}"):
            var_path = ref[2:-1]
        else:
            var_path = ref

        # 环境变量
        if var_path.startswith("env."):
            env_key = var_path[4:]
            return self._get_env_variable(env_key)

        # 从变量字典中查找
        return self.variables.get(var_path)

    def resolve_all_variables(self, node_data: dict) -> dict[str, Any]:
        """
        解析节点配置中所有变量引用，返回扁平化的变量字典。
        """
        return self.variables

    def get_node_inputs(self, node_id: str, node_data: dict) -> dict[str, Any]:
        """获取节点的输入数据（用于记录到 ExecutionNode）"""
        input_mapping = node_data.get("input_mapping", {})
        resolved = {}
        resolver = VariableResolver()
        for key, template in input_mapping.items():
            resolved[key] = resolver.resolve(template, self.variables)
        return resolved

    def get_end_outputs(self) -> dict[str, Any]:
        """收集所有结束节点的输出"""
        end_outputs = {}
        for node in self._nodes_data:
            if node["type"] == "endNode":
                output_mapping = node.get("data", {}).get("output_mapping", {})
                resolver = VariableResolver()
                for key, template in output_mapping.items():
                    end_outputs[key] = resolver.resolve(template, self.variables)
        return end_outputs

    def get_branch_nodes(self, parallel_node_id: str, branch_id: str) -> list[dict]:
        """获取并行节点某个分支内的子节点"""
        # 找到从 parallel 节点出发，经过指定 branch 的所有节点
        branch_edges = [
            e for e in self._edges_data
            if e.get("source") == parallel_node_id
            and e.get("sourceHandle") == branch_id
        ]
        # BFS 收集分支内所有节点
        result = []
        visited = set()
        queue = [e["target"] for e in branch_edges]

        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            if nid in self._node_map:
                result.append(self._node_map[nid])
            # 找后续节点
            for edge in self._edges_data:
                if edge["source"] == nid:
                    queue.append(edge["target"])

        return result

    def get_loop_child_nodes(self, loop_node_id: str) -> list[dict]:
        """获取循环节点内部的子节点"""
        # 类似并行分支，找到循环体内的所有节点
        loop_edges = [
            e for e in self._edges_data
            if e.get("source") == loop_node_id
        ]
        result = []
        visited = set()
        queue = [e["target"] for e in loop_edges]

        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            if nid in self._node_map:
                result.append(self._node_map[nid])
            for edge in self._edges_data:
                if edge["source"] == nid:
                    queue.append(edge["target"])

        return result

    async def _get_env_variable(self, key: str) -> Optional[str]:
        """获取环境变量（带缓存）"""
        if key in self._env_cache:
            return self._env_cache[key]

        from sqlalchemy import select
        from app.models.env_variable import EnvVariable
        from app.core.encryption import decrypt_value

        result = await self.db_session.execute(
            select(EnvVariable).where(
                EnvVariable.user_id == self.user_id,
                EnvVariable.key == key,
            )
        )
        env_var = result.scalar_one_or_none()
        if env_var:
            value = decrypt_value(env_var.value_encrypted)
            self._env_cache[key] = value
            return value
        return None


# 需要在这里导入，避免循环引用
from app.services.execution.variable_resolver import VariableResolver
```

### 3.5 拓扑排序算法

```python
# app/services/execution/topo_sorter.py

from collections import deque
from typing import Optional


class TopoSorter:
    """
    工作流拓扑排序器。
    
    使用 Kahn 算法（BFS 拓扑排序）确定节点执行顺序。
    
    特殊处理：
    - 条件分支节点：只保留匹配分支的后续节点
    - 并行执行节点：同一深度的并行分支节点可以并发
    - 循环节点：内部子节点在每次迭代时执行
    
    返回格式：
    [
        {
            "node": {...},          # 原始节点数据
            "depth": int,           # 拓扑深度（用于判断可并行的节点）
            "group": str | None,    # 所属组（parallel_1, loop_1 等）
            "skip": False,          # 初始为 False，运行时根据条件分支更新
        },
        ...
    ]
    """

    def __init__(self, nodes_data: list[dict], edges_data: list[dict]):
        self.nodes_data = nodes_data
        self.edges_data = edges_data
        self._node_map = {n["id"]: n for n in nodes_data}
        self._skip_set: set[str] = set()

    def sort(self) -> list[dict]:
        """
        执行拓扑排序。
        
        算法步骤（Kahn 算法）：
        1. 构建有向图 + 计算入度
        2. 入度为 0 的节点入队
        3. 逐层出队，每层节点可以并行执行
        4. 返回排序后的节点列表
        """
        node_ids = {n["id"] for n in self.nodes_data}

        # 构建邻接表和入度表
        adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}

        for edge in self.edges_data:
            source = edge.get("source")
            target = edge.get("target")
            if source in node_ids and target in node_ids:
                adjacency[source].append(target)
                in_degree[target] = in_degree.get(target, 0) + 1

        # BFS 分层拓扑排序
        result = []
        depth = 0
        queue = deque([nid for nid in node_ids if in_degree[nid] == 0])

        while queue:
            # 当前层的所有节点
            layer_size = len(queue)
            for _ in range(layer_size):
                nid = queue.popleft()
                node = self._node_map.get(nid)
                if node:
                    result.append({
                        "node": node,
                        "depth": depth,
                        "group": self._determine_group(nid),
                        "skip": False,
                    })

                # 减少邻居入度
                for neighbor in adjacency.get(nid, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            depth += 1

        return result

    def _determine_group(self, node_id: str) -> Optional[str]:
        """判断节点是否属于某个并行/循环组"""
        for edge in self.edges_data:
            if edge.get("target") == node_id:
                source_node = self._node_map.get(edge.get("source"))
                if source_node:
                    if source_node["type"] == "parallelNode":
                        return f"parallel_{edge['source']}"
                    elif source_node["type"] == "loopNode":
                        return f"loop_{edge['source']}"
        return None

    def mark_branch_result(
        self,
        condition_node_id: str,
        matched_branch_id: Optional[str],
        edges_data: list[dict],
    ):
        """
        条件分支执行后，标记未匹配的分支路径上的节点为 skip。
        
        算法：
        1. 找到条件节点的所有出边
        2. 匹配分支的出边保留
        3. 未匹配分支的出边 → BFS 遍历所有下游节点 → 加入 skip_set
        """
        # 找到条件节点的所有出边
        condition_edges = [
            e for e in edges_data
            if e.get("source") == condition_node_id
        ]

        for edge in condition_edges:
            source_handle = edge.get("sourceHandle", "")
            # 如果这个分支未匹配
            if source_handle != matched_branch_id:
                # BFS 标记所有下游节点为 skip
                target_id = edge.get("target")
                if target_id:
                    self._mark_downstream_skip(target_id, edges_data)

    def _mark_downstream_skip(self, start_id: str, edges_data: list[dict]):
        """BFS 标记所有下游节点"""
        queue = deque([start_id])
        visited = set()

        while queue:
            nid = queue.popleft()
            if nid in visited:
                continue
            visited.add(nid)
            self._skip_set.add(nid)

            for edge in edges_data:
                if edge.get("source") == nid:
                    queue.append(edge.get("target"))

    def should_skip(self, node_id: str) -> bool:
        """判断节点是否应被跳过"""
        return node_id in self._skip_set
```

**拓扑排序伪代码**：

```
function topologicalSort(nodes, edges):
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
    
    // BFS 分层排序
    queue = all nodes where inDegree == 0
    result = []
    depth = 0
    
    while queue is not empty:
        layerSize = queue.length
        for i = 0; i < layerSize; i++:
            node = queue.dequeue()
            result.append({node, depth, group: determineGroup(node)})
            
            for each neighbor in graph[node.id]:
                inDegree[neighbor] -= 1
                if inDegree[neighbor] == 0:
                    queue.enqueue(neighbor)
        
        depth++
    
    return result

function determineGroup(nodeId):
    for each edge in edges:
        if edge.target == nodeId:
            sourceNode = getNode(edge.source)
            if sourceNode.type == "parallelNode":
                return "parallel_" + edge.source
            if sourceNode.type == "loopNode":
                return "loop_" + edge.source
    return null
```

### 3.6 变量解析引擎

```python
# app/services/execution/variable_resolver.py

import re
from typing import Any, Optional


class VariableResolver:
    """
    变量解析引擎。
    
    负责将模板字符串中的 ${...} 变量引用替换为实际值。
    
    支持的引用格式：
    - ${node_id.var_name} → 节点输出变量
    - ${input.param_name} → 全局输入参数
    - ${env.VAR_NAME} → 环境变量
    - ${current_item} → 循环迭代变量
    
    正则匹配模式：
    \\$\\{([^}]+)\\}
    
    解析规则：
    1. 如果整个字符串是一个变量引用（如 "${node_1.result}"），返回原始类型
    2. 如果字符串中混合了文本和引用（如 "Hello ${node_1.name}"），返回字符串
    3. 如果变量未找到，保留原始引用文本
    """

    # 匹配 ${...} 的正则
    VAR_PATTERN = re.compile(r'\$\{([^}]+)\}')

    def resolve(self, template: Any, variables: dict[str, Any]) -> Any:
        """
        解析模板中的变量引用。
        
        Args:
            template: 模板值（可以是 str、dict、list、或其他类型）
            variables: 可用变量字典（key 为 "node_id.var_name" 格式）
        
        Returns:
            解析后的值
        """
        if isinstance(template, str):
            return self._resolve_string(template, variables)
        elif isinstance(template, dict):
            return {k: self.resolve(v, variables) for k, v in template.items()}
        elif isinstance(template, list):
            return [self.resolve(item, variables) for item in template]
        else:
            return template

    def _resolve_string(self, template: str, variables: dict[str, Any]) -> Any:
        """
        解析字符串模板。
        
        关键逻辑：
        - 如果整个字符串恰好是 "${var_ref}" 格式，返回原始类型（保留 dict/list/int 等）
        - 如果字符串中混合了文本，返回拼接后的字符串
        """
        # 检查是否是完整的单一引用
        if template.startswith("${") and template.endswith("}") and template.count("${") == 1:
            var_path = template[2:-1]
            value = variables.get(var_path)
            if value is not None:
                return value
            # 环境变量特殊处理（返回原始引用，由 ExecutionContext 处理）
            if var_path.startswith("env."):
                return template
            return template  # 变量未找到，保留原样

        # 多引用或混合文本
        def replacer(match):
            var_path = match.group(1)
            value = variables.get(var_path)
            if value is not None:
                return str(value)
            return match.group(0)  # 未找到，保留原样

        return self.VAR_PATTERN.sub(replacer, template)

    def resolve_env_variables(
        self,
        template: Any,
        env_resolver_func,
    ) -> Any:
        """
        解析环境变量引用 ${env.XXX}。
        
        Args:
            template: 模板值
            env_resolver_func: 环境变量解析回调函数 (key: str) -> str
        
        Returns:
            解析后的值
        """
        if isinstance(template, str):
            return self._resolve_env_string(template, env_resolver_func)
        elif isinstance(template, dict):
            return {k: self.resolve_env_variables(v, env_resolver_func) for k, v in template.items()}
        elif isinstance(template, list):
            return [self.resolve_env_variables(item, env_resolver_func) for item in template]
        else:
            return template

    def _resolve_env_string(self, template: str, env_resolver_func) -> str:
        """解析字符串中的环境变量"""
        def replacer(match):
            var_path = match.group(1)
            if var_path.startswith("env."):
                env_key = var_path[4:]
                value = env_resolver_func(env_key)
                return value if value is not None else match.group(0)
            return match.group(0)

        return self.VAR_PATTERN.sub(replacer, template)

    def extract_refs(self, obj: Any) -> list[str]:
        """
        递归提取对象中所有 ${...} 变量引用。
        用于校验阶段。
        """
        refs = []
        if isinstance(obj, str):
            matches = self.VAR_PATTERN.findall(obj)
            refs.extend(matches)
        elif isinstance(obj, dict):
            for value in obj.values():
                refs.extend(self.extract_refs(value))
        elif isinstance(obj, list):
            for item in obj:
                refs.extend(self.extract_refs(item))
        return refs
```

**变量解析伪代码**：

```
function resolveVariable(template, variables):
    if template is not a string:
        return template
    
    // 单一引用：整个字符串就是 "${var_ref}"
    if template matches /^\$\{([^}]+)\}$/;
        varPath = extractVarPath(template)
        value = variables[varPath]
        return value ?? template  // 未找到返回原样
    
    // 混合引用：字符串中包含多个 ${...}
    return template.replaceAll(/\$\{([^}]+)\}/g, (match) => {
        varPath = extractVarPath(match)
        value = variables[varPath]
        return value ?? match
    })
```

### 3.7 执行流程伪代码（完整）

```
async function executeWorkflow(execution, nodesData, edgesData, inputData, userId):
    // 1. 初始化
    ctx = new ExecutionContext(execution.id, userId, db, redis)
    ctx.setGlobalInput(inputData)
    ctx.setGraph(nodesData, edgesData)
    
    // 2. 拓扑排序
    sorter = new TopoSorter(nodesData, edgesData)
    executionOrder = sorter.sort()
    
    // 3. 更新状态为 running
    execution.status = "running"
    broadcast({type: "execution_status", status: "running"})
    
    try:
        // 4. 按顺序执行节点
        for step in executionOrder:
            node = step.node
            nodeId = node.id
            nodeType = node.type
            
            // 4a. 检查取消
            if cancellationMgr.isCancelled(execution.id):
                execution.status = "cancelled"
                broadcast({type: "execution_status", status: "cancelled"})
                return
            
            // 4b. 跳过未命中分支的节点
            if step.skip:
                createExecutionNode(nodeId, status: "skipped")
                broadcast({type: "node_status_change", node_id: nodeId, status: "skipped"})
                continue
            
            // 4c. 执行节点
            result = await executeNode(execution, node, ctx)
            
            // 4d. 条件分支：标记后续节点的 skip 状态
            if nodeType == "conditionNode":
                matchedBranch = result.output.matched_branch
                sorter.markBranchResult(nodeId, matchedBranch, edgesData)
                for futureStep in executionOrder.remaining():
                    if sorter.shouldSkip(futureStep.node.id):
                        futureStep.skip = true
        
        // 5. 执行成功
        execution.status = "success"
        execution.output_data = ctx.getEndOutputs()
        execution.total_duration_ms = elapsed(start)
        broadcast({type: "execution_status", status: "success", output: execution.output_data})
    
    catch ReviewPausedException:
        execution.status = "paused"
        // 等待审核恢复（通过 Redis Pub/Sub）
        reviewResult = await reviewMgr.waitForReview(execution.id, nodeId, timeout)
        // 审核完成后继续执行（重新调用 executeWorkflow 从暂停点继续）
    
    catch Exception as e:
        execution.status = "failed"
        broadcast({type: "error", error_message: e.message})
    
    finally:
        save(execution)
```

---

## 4. 每种节点类型的执行器

### 4.1 StartExecutor（开始节点）

```python
# app/services/node_executors/start_executor.py

from .base import BaseNodeExecutor, NodeExecutionResult, ExecutionContext


class StartExecutor(BaseNodeExecutor):
    """
    开始节点执行器。
    
    输入/输出定义：
    - 输入：全局输入参数（来自 WorkflowRunRequest.input_data）
    - 输出：将输入参数透传到上下文
    
    执行逻辑：
    1. 从 ExecutionContext 获取全局输入
    2. 根据节点定义的 inputs 校验必填参数
    3. 将输入参数作为输出存入上下文
    
    示例：
    - 节点定义 inputs: [{name: "user_query", type: "string", required: true}]
    - 全局输入: {"user_query": "帮我写一个函数"}
    - 输出: {"user_query": "帮我写一个函数"}
    """

    async def execute(self, config, input_variables, context):
        # 开始节点的输入就是全局输入
        node_inputs = config.get("inputs", [])
        output = {}

        for input_def in node_inputs:
            name = input_def["name"]
            required = input_def.get("required", False)
            default_value = input_def.get("default_value")

            value = context._global_input.get(name)
            if value is None:
                if required:
                    return NodeExecutionResult(
                        error=f"缺少必填输入参数: {name}",
                        duration_ms=0,
                    )
                value = default_value

            output[name] = value

        return NodeExecutionResult(output=output, duration_ms=0)
```

### 4.2 EndExecutor（结束节点）

```python
# app/services/node_executors/end_executor.py


class EndExecutor(BaseNodeExecutor):
    """
    结束节点执行器。
    
    输入/输出定义：
    - 输入：通过 output_mapping 引用上游节点输出
    - 输出：收集指定的输出变量，生成最终结果
    
    执行逻辑：
    1. 解析 output_mapping 中的所有变量引用
    2. 将解析后的值作为最终输出
    3. 一个工作流可以有多个结束节点，每个收集不同的输出
    
    示例：
    - output_mapping: {"final_answer": "${node_agent_1.result}", "refs": "${node_kb_1.docs}"}
    - 输出: {"final_answer": "...", "refs": [...]}
    """

    async def execute(self, config, input_variables, context):
        output_mapping = config.get("output_mapping", {})
        from app.services.execution.variable_resolver import VariableResolver
        resolver = VariableResolver()

        output = {}
        for key, template in output_mapping.items():
            output[key] = resolver.resolve(template, input_variables)

        return NodeExecutionResult(output=output, duration_ms=0)
```

### 4.3 AgentExecutor（Agent 节点）- Phase 5 扩展

```python
# app/services/node_executors/agent_executor.py（Phase 5 扩展版）

class AgentExecutor(BaseNodeExecutor):
    """
    Agent 节点执行器（工作流执行版本）。
    
    与 Phase 4 单节点调试版本的区别：
    1. 支持重试机制（LLM 调用失败时自动重试）
    2. 支持超时控制
    3. 记录 Token 消耗到 ModelUsage 表
    4. 通过 ExecutionContext 广播日志
    
    输入/输出定义：
    - 输入：input_mapping 映射的变量
    - 输出：{output_key: LLM回复内容}
    
    执行逻辑：
    1. 查询 Agent 配置（system_prompt, model, temperature 等）
    2. 查询 Model + Provider（API Key）
    3. 构建 messages（system_prompt + 用户输入）
    4. 调用 LLM API（带重试）
    5. 记录 Token 消耗
    6. 返回 LLM 输出
    
    重试策略：
    - 最大重试次数：3
    - 重试间隔：指数退避（1s, 2s, 4s）
    - 仅对 5xx 错误和超时重试，4xx 不重试
    """

    DEFAULT_TIMEOUT = 120
    MAX_RETRIES = 3

    async def execute(self, config, input_variables, context):
        start_time = time.time()

        agent_id = config.get("agent_id")
        if not agent_id:
            return NodeExecutionResult(error="agent_id is required", duration_ms=0)

        # 查询 Agent
        agent = await self._get_agent(context, agent_id)
        if not agent:
            return NodeExecutionResult(error=f"Agent {agent_id} not found", duration_ms=self._elapsed(start_time))

        # 查询 Model + Provider
        model, provider = await self._get_model_and_provider(context, agent)
        if not model or not provider:
            return NodeExecutionResult(error="Model/Provider not configured", duration_ms=self._elapsed(start_time))

        # 解密 API Key
        from app.core.encryption import decrypt_value
        api_key = decrypt_value(provider.api_key_encrypted)

        # 解析输入
        from app.services.execution.variable_resolver import VariableResolver
        resolver = VariableResolver()
        input_mapping = config.get("input_mapping", {})
        resolved_inputs = {k: resolver.resolve(v, input_variables) for k, v in input_mapping.items()}
        user_input = " ".join(str(v) for v in resolved_inputs.values())

        # 构建 messages
        messages = []
        if agent.system_prompt:
            # 解析 system_prompt 中的变量引用
            system_prompt = resolver.resolve(agent.system_prompt, input_variables)
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_input})

        # 调用 LLM API（带重试）
        timeout = self._resolve_timeout(config)
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                llm_result = await self._call_llm(
                    provider_type=provider.provider_type if hasattr(provider, 'provider_type') else "openai",
                    api_key=api_key,
                    base_url=getattr(provider, 'base_url', None),
                    model_name=agent.model_name,
                    messages=messages,
                    temperature=agent.temperature,
                    max_tokens=agent.max_tokens,
                    timeout=timeout,
                )

                # 记录 Token 消耗
                tokens = llm_result.get("total_tokens", 0)
                await self._record_usage(context, agent, tokens)

                output_key = config.get("output_key", "result")
                return NodeExecutionResult(
                    output={output_key: llm_result["content"]},
                    duration_ms=self._elapsed(start_time),
                    tokens_used=tokens,
                )

            except httpx.TimeoutException:
                last_error = "LLM API call timed out"
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)  # 指数退避
                    continue
            except httpx.HTTPStatusError as e:
                if 500 <= e.response.status_code < 600:
                    last_error = f"LLM API server error: {e.response.status_code}"
                    if attempt < self.MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                else:
                    last_error = f"LLM API error: {e.response.status_code}"
                    break
            except Exception as e:
                last_error = str(e)
                break

        return NodeExecutionResult(error=last_error, duration_ms=self._elapsed(start_time))

    async def _record_usage(self, context, agent, tokens):
        """记录 Token 消耗到 ModelUsage 表"""
        from datetime import date
        from app.models.model_provider import ModelUsage
        
        usage = ModelUsage(
            user_id=context.user_id,
            provider_name=agent.model_provider or "unknown",
            model_name=agent.model_name or "unknown",
            input_tokens=tokens,
            output_tokens=0,
            cost=0,
            date=date.today(),
        )
        context.db_session.add(usage)
        await context.db_session.flush()
```

### 4.4 KnowledgeRetrievalExecutor（知识检索节点）- Phase 5 扩展

```python
# app/services/node_executors/knowledge_executor.py

class KnowledgeRetrievalExecutor(BaseNodeExecutor):
    """
    知识检索节点执行器（工作流执行版本）。
    
    输入/输出定义：
    - 输入：query_template 解析后的查询文本
    - 输出：{output_key: [{content, chunk_index, similarity}, ...]}
    
    执行逻辑：
    1. 解析 query_template 获取查询文本
    2. 调用 Embedding API 向量化
    3. pgvector 余弦相似度搜索
    4. 按 score_threshold 过滤
    5. 返回 Top-K 结果
    
    特殊处理：
    - Embedding 调用失败时返回错误
    - 知识库不存在时返回错误
    - 无结果时返回空数组（不报错）
    """

    async def execute(self, config, input_variables, context):
        start_time = time.time()

        kb_id = config.get("knowledge_base_id")
        if not kb_id:
            return NodeExecutionResult(error="knowledge_base_id is required", duration_ms=self._elapsed(start_time))

        # 解析查询文本
        from app.services.execution.variable_resolver import VariableResolver
        resolver = VariableResolver()
        query_template = config.get("query_template", "")
        query = resolver.resolve(query_template, input_variables)
        if not query or not str(query).strip():
            return NodeExecutionResult(error="Query text is empty after resolution", duration_ms=self._elapsed(start_time))

        top_k = config.get("top_k", 5)
        score_threshold = config.get("score_threshold", 0.0)

        # 向量化
        embedding = await self._get_embedding(query, context)
        if not embedding:
            return NodeExecutionResult(error="Failed to get embedding for query", duration_ms=self._elapsed(start_time))

        # 向量搜索
        results = await self._vector_search(kb_id, embedding, top_k, score_threshold, context)

        output_key = config.get("output_key", "retrieved_docs")
        return NodeExecutionResult(
            output={output_key: results},
            duration_ms=self._elapsed(start_time),
        )
    # _get_embedding 和 _vector_search 复用 Phase 4 实现
```

### 4.5 ConditionExecutor（条件分支节点）- Phase 5 扩展

```python
# app/services/node_executors/condition_executor.py

class ConditionExecutor(BaseNodeExecutor):
    """
    条件分支节点执行器（工作流执行版本）。
    
    输入/输出定义：
    - 输入：conditions 中各变量的当前值
    - 输出：{matched_branch: "branch_id"} 匹配分支 ID
    
    执行逻辑：
    1. 遍历 conditions 列表
    2. 解析每个 condition 的 variable 引用
    3. 按顺序评估条件（短路求值：第一个匹配即停止）
    4. 找到匹配分支 ID 或默认分支
    5. 输出 matched_branch 供 WorkflowExecutor 进行路由
    
    支持的操作符：
    - equals / not_equals
    - contains / not_contains
    - starts_with / ends_with
    - regex
    - is_empty / is_not_empty
    - gt / gte / lt / lte
    
    特殊处理：
    - 变量类型自动转换（数值比较时自动转 float）
    - 正则编译缓存
    - 无匹配时使用默认分支（condition_id=null 的分支）
    - 无默认分支时返回 matched_branch=null，后续节点全部跳过
    """

    async def execute(self, config, input_variables, context):
        start_time = time.time()

        conditions = config.get("conditions", [])
        branches = config.get("branches", [])

        from app.services.execution.variable_resolver import VariableResolver
        resolver = VariableResolver()

        matched_branch_id = None
        for condition in conditions:
            variable_ref = condition.get("variable", "")
            operator = condition.get("operator", "equals")
            expected = condition.get("value")

            actual = resolver.resolve(variable_ref, input_variables)

            if self._evaluate(actual, operator, expected):
                cond_id = condition.get("id")
                for branch in branches:
                    if branch.get("condition_id") == cond_id:
                        matched_branch_id = branch["id"]
                        break
                break

        if not matched_branch_id:
            for branch in branches:
                if branch.get("condition_id") is None:
                    matched_branch_id = branch["id"]
                    break

        return NodeExecutionResult(
            output={"matched_branch": matched_branch_id},
            duration_ms=self._elapsed(start_time),
        )
    # _evaluate 方法复用 Phase 4 实现
```

### 4.6 ParallelExecutor（并行执行节点）- Phase 5 重写

```python
# app/services/node_executors/parallel_executor.py

class ParallelExecutor(BaseNodeExecutor):
    """
    并行执行节点执行器（工作流执行版本）。
    
    输入/输出定义：
    - 输入：分支共享的上下文变量
    - 输出：{parallel_result: {branch_0: {...}, branch_1: {...}}}
    
    执行逻辑（在 WorkflowExecutor._execute_parallel 中实现）：
    1. 获取 branches 配置
    2. 对每个分支，找到分支内的所有子节点
    3. 使用 asyncio.gather 并发执行所有分支
    4. 等待全部完成（wait_mode=all）或任一完成（wait_mode=any）
    5. 合并所有分支的输出
    
    特殊处理：
    - 分支内节点按拓扑顺序执行
    - 分支间完全隔离（不共享中间变量）
    - 某分支失败时，根据配置决定是否取消其他分支
    - wait_mode=any 时，取消未完成的分支
    
    注意：实际并行逻辑在 WorkflowExecutor._execute_parallel 中实现，
    此执行器仅用于单节点调试模式。
    """

    async def execute(self, config, input_variables, context):
        # 单节点调试模式：模拟并行输出
        branches = config.get("branches", [])
        output = {"parallel_status": "simulated", "branches": []}
        for branch in branches:
            output["branches"].append({
                "branch_id": branch["id"],
                "label": branch.get("label", ""),
                "status": "simulated",
            })
        return NodeExecutionResult(output=output, duration_ms=0)
```

### 4.7 LoopExecutor（循环/迭代节点）- Phase 5 重写

```python
# app/services/node_executors/loop_executor.py

class LoopExecutor(BaseNodeExecutor):
    """
    循环/迭代节点执行器（工作流执行版本）。
    
    输入/输出定义：
    - 输入：loop_variable 引用的数组
    - 输出：{loop_results: [{index, item, output}, ...], total_iterations: int}
    
    执行逻辑（在 WorkflowExecutor._execute_loop 中实现）：
    1. 解析 loop_variable 获取要遍历的数组
    2. 获取循环体子节点
    3. 对每个元素：
       a. 设置 item_name = 当前元素, index_name = 当前索引
       b. 执行循环体子节点
       c. 收集每次迭代的输出
    4. 返回所有迭代结果
    
    特殊处理：
    - 循环变量不是数组时报错
    - 每次迭代可以检查取消标志
    - 最大迭代次数限制（防止死循环，默认 1000）
    - 迭代变量在子节点中可通过 ${item_name} 和 ${index_name} 引用
    
    注意：实际循环逻辑在 WorkflowExecutor._execute_loop 中实现。
    """

    MAX_ITERATIONS = 1000

    async def execute(self, config, input_variables, context):
        # 单节点调试模式：只执行一次迭代
        loop_var_ref = config.get("loop_variable", "")
        from app.services.execution.variable_resolver import VariableResolver
        resolver = VariableResolver()
        loop_array = resolver.resolve(loop_var_ref, input_variables)

        if not isinstance(loop_array, list):
            return NodeExecutionResult(error="Loop variable is not an array", duration_ms=0)

        item_name = config.get("item_name", "item")
        index_name = config.get("index_name", "index")

        # 调试模式只执行第一次迭代
        if len(loop_array) > 0:
            output = {
                "loop_results": [{
                    "index": 0,
                    "item": loop_array[0],
                    "output": {"debug": True},
                }],
                "total_iterations": 1,
                "total_items": len(loop_array),
            }
        else:
            output = {"loop_results": [], "total_iterations": 0, "total_items": 0}

        return NodeExecutionResult(output=output, duration_ms=0)
```

### 4.8 ReviewExecutor（审核节点）- Phase 5 新增

```python
# app/services/node_executors/review_executor.py

class ReviewExecutor(BaseNodeExecutor):
    """
    审核节点执行器（工作流执行版本）。
    
    输入/输出定义：
    - 输入：上游节点的输出数据（供审核人查看）
    - 输出：取决于审核操作
      - approve: {review_action: "approved", review_comment: "..."}
      - reject: {review_action: "rejected", review_comment: "..."}
      - modify: 修改后的数据
    
    执行逻辑（在 WorkflowExecutor._execute_review 中实现）：
    1. 广播审核请求到前端（WebSocket）
    2. 暂停工作流执行（抛出 ReviewPausedException）
    3. 通过 ReviewManager 等待审核结果
    4. 收到结果后恢复执行
    
    审核配置：
    - reviewer_ids: 审核人列表
    - timeout_seconds: 超时时间（默认 3600 秒）
    - on_timeout: 超时行为（approve | reject）
    
    审核数据结构（ReviewActionRequest）：
    {
        "action": "approve" | "reject" | "modify",
        "modified_data": {...},  // 仅 modify 时
        "comment": "审核意见"
    }
    
    注意：实际暂停/恢复逻辑在 WorkflowExecutor._execute_review 中实现。
    此执行器仅用于单节点调试模式（直接返回模拟审核通过）。
    """

    async def execute(self, config, input_variables, context):
        # 单节点调试模式：直接模拟审核通过
        return NodeExecutionResult(
            output={
                "review_action": "approved",
                "review_comment": "单节点调试模式自动通过",
            },
            duration_ms=0,
        )
```

### 4.9 TestExecutor（测试节点）- Phase 5 新增

```python
# app/services/node_executors/test_executor.py

class TestExecutor(BaseNodeExecutor):
    """
    测试节点执行器。
    
    输入/输出定义：
    - 输入：assertions 中各变量的当前值
    - 输出：{test_results: [{variable, operator, passed, actual, expected}, ...], all_passed: bool}
    
    执行逻辑：
    1. 遍历 assertions 列表
    2. 对每个断言：解析变量值，应用操作符，判断通过/失败
    3. 汇总所有断言结果
    4. 如果有断言失败：
       - on_failure == "continue"：继续执行
       - on_failure == "abort"：抛出异常终止执行
       - on_failure == "retry"：重试上游节点（最多 retry_count 次）
    
    支持的断言操作符（复用条件节点的操作符）：
    - equals / not_equals
    - contains / not_contains
    - is_empty / is_not_empty
    - gt / gte / lt / lte
    - regex
    
    示例配置：
    {
        "assertions": [
            {"variable": "${node_agent_1.result}", "operator": "is_not_empty"},
            {"variable": "${node_agent_1.result}", "operator": "contains", "expected": "function"}
        ],
        "on_failure": "abort",
        "retry_count": 3
    }
    """

    async def execute(self, config, input_variables, context):
        start_time = time.time()

        assertions = config.get("assertions", [])
        on_failure = config.get("on_failure", "continue")

        from app.services.execution.variable_resolver import VariableResolver
        resolver = VariableResolver()

        results = []
        all_passed = True

        for assertion in assertions:
            variable_ref = assertion.get("variable", "")
            operator = assertion.get("operator", "is_not_empty")
            expected = assertion.get("expected")

            actual = resolver.resolve(variable_ref, input_variables)
            passed = self._evaluate(actual, operator, expected)

            results.append({
                "variable": variable_ref,
                "operator": operator,
                "expected": expected,
                "actual": actual,
                "passed": passed,
            })

            if not passed:
                all_passed = False

        output = {
            "test_results": results,
            "all_passed": all_passed,
            "passed_count": sum(1 for r in results if r["passed"]),
            "failed_count": sum(1 for r in results if not r["passed"]),
        }

        # 处理失败情况
        if not all_passed:
            if on_failure == "abort":
                return NodeExecutionResult(
                    output=output,
                    duration_ms=self._elapsed(start_time),
                    error=f"测试失败: {output['failed_count']} 个断言未通过",
                )
            elif on_failure == "retry":
                # 重试逻辑在 WorkflowExecutor 中处理
                output["retry_requested"] = True
                output["retry_count"] = config.get("retry_count", 3)

        return NodeExecutionResult(output=output, duration_ms=self._elapsed(start_time))

    def _evaluate(self, actual, operator, expected) -> bool:
        """评估断言（复用条件节点的操作符逻辑）"""
        if operator == "equals":
            return str(actual) == str(expected)
        elif operator == "not_equals":
            return str(actual) != str(expected)
        elif operator == "contains":
            return str(expected) in str(actual or "")
        elif operator == "not_contains":
            return str(expected) not in str(actual or "")
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
        elif operator == "regex":
            import re
            return bool(re.search(str(expected), str(actual or "")))
        return False
```

### 4.10 DelayExecutor（延时等待节点）- Phase 5 扩展

```python
# app/services/node_executors/delay_executor.py

class DelayExecutor(BaseNodeExecutor):
    """
    延时等待节点执行器（工作流执行版本）。
    
    输入/输出定义：
    - 输入：无特定输入
    - 输出：{delayed_seconds: float}
    
    执行逻辑：
    1. 获取 delay_seconds 配置
    2. asyncio.sleep(delay_seconds)
    3. 支持取消：在等待期间检查取消标志
    
    特殊处理（工作流执行 vs 单节点调试）：
    - 工作流执行：完整等待指定时间，期间定期检查取消标志
    - 单节点调试：最多等待 5 秒
    """

    async def execute(self, config, input_variables, context):
        start_time = time.time()
        delay = config.get("delay_seconds", 1)

        # 工作流执行模式：分段等待，每段检查取消
        remaining = delay
        while remaining > 0:
            # 检查取消
            if hasattr(context, 'cancellation_mgr') and context.cancellation_mgr:
                if await context.cancellation_mgr.is_cancelled(context.execution_id):
                    return NodeExecutionResult(
                        output={"delayed_seconds": delay - remaining, "cancelled": True},
                        duration_ms=self._elapsed(start_time),
                    )

            # 每次最多等待 1 秒
            sleep_time = min(1.0, remaining)
            await asyncio.sleep(sleep_time)
            remaining -= sleep_time

        return NodeExecutionResult(
            output={"delayed_seconds": delay},
            duration_ms=self._elapsed(start_time),
        )
```

### 4.11 CodeExecutor（代码执行节点）- Phase 5 扩展

```python
# app/services/node_executors/code_executor.py

class CodeExecutor(BaseNodeExecutor):
    """
    代码执行节点执行器（工作流执行版本）。
    
    输入/输出定义：
    - 输入：input_mapping 映射的变量
    - 输出：{output_key: main() 函数返回值}
    
    执行逻辑：
    1. 安全检查（禁止危险模块/函数）
    2. 解析输入变量
    3. 包装用户代码
    4. 在子进程中执行（隔离环境）
    5. 捕获输出/错误
    6. 清理临时资源
    
    沙箱安全限制：
    - 最大执行时间: 30 秒
    - 禁止网络访问（禁止 http/urllib/requests/socket 等模块）
    - 禁止文件系统访问（禁止 os/sys/shutil 等模块）
    - 禁止 subprocess / eval / exec / __import__
    - 内存限制: 256MB（通过 subprocess 资源限制）
    - stdout 输出限制: 256KB
    
    代码规范：
    - Python: 定义 main(input_data: dict) -> dict
    - JavaScript: 定义 function main(inputData) { return {...} }
    """

    DEFAULT_TIMEOUT = 30
    BLOCKED_MODULES = {
        "os", "sys", "subprocess", "socket", "shutil", "ctypes",
        "importlib", "signal", "multiprocessing", "threading",
        "http", "urllib", "requests", "httpx", "asyncio",
        "aiohttp", "websockets", "pickle", "marshal",
    }

    async def execute(self, config, input_variables, context):
        start_time = time.time()
        language = config.get("language", "python")
        code = config.get("code", "")
        timeout = min(self._resolve_timeout(config), self.DEFAULT_TIMEOUT)

        if not code:
            return NodeExecutionResult(error="Code is empty", duration_ms=self._elapsed(start_time))

        # 安全检查
        security_error = self._security_check(code, language)
        if security_error:
            return NodeExecutionResult(error=security_error, duration_ms=self._elapsed(start_time))

        # 解析输入
        from app.services.execution.variable_resolver import VariableResolver
        resolver = VariableResolver()
        input_mapping = config.get("input_mapping", {})
        resolved_inputs = {k: resolver.resolve(v, input_variables) for k, v in input_mapping.items()}

        try:
            if language == "python":
                result = await self._execute_python(code, resolved_inputs, timeout)
            elif language == "javascript":
                result = await self._execute_javascript(code, resolved_inputs, timeout)
            else:
                return NodeExecutionResult(error=f"Unsupported language: {language}", duration_ms=self._elapsed(start_time))

            # 检查执行结果是否有错误
            if isinstance(result, dict) and "error" in result:
                return NodeExecutionResult(error=result["error"], duration_ms=self._elapsed(start_time))

            output_key = config.get("output_key", "code_result")
            return NodeExecutionResult(
                output={output_key: result},
                duration_ms=self._elapsed(start_time),
            )
        except asyncio.TimeoutError:
            return NodeExecutionResult(error=f"Code execution timed out ({timeout}s)", duration_ms=self._elapsed(start_time))
        except Exception as e:
            return NodeExecutionResult(error=str(e), duration_ms=self._elapsed(start_time))
    # _security_check, _execute_python, _execute_javascript 复用 Phase 4 实现
```

### 4.12 HTTPExecutor（HTTP 请求节点）- Phase 5 扩展

```python
# app/services/node_executors/http_executor.py

class HTTPExecutor(BaseNodeExecutor):
    """
    HTTP 请求节点执行器（工作流执行版本）。
    
    输入/输出定义：
    - 输入：URL/Headers/Body 中的变量引用
    - 输出：{output_key: response_body, output_key_status: status_code, output_key_headers: headers}
    
    执行逻辑：
    1. 解析 URL 中的变量
    2. SSRF 防护检查
    3. 解析 Headers/Body/Auth 中的变量
    4. 发起 HTTP 请求
    5. 检查响应大小
    6. 返回响应
    
    安全限制：
    - 禁止访问内网 IP（SSRF 防护）
    - 仅支持 HTTP/HTTPS
    - 最大响应体 1MB
    - 最大超时 60 秒
    - 禁止跟随重定向到内网地址
    """

    DEFAULT_TIMEOUT = 30
    MAX_RESPONSE_SIZE = 1024 * 1024

    async def execute(self, config, input_variables, context):
        # 工作流执行版本与 Phase 4 基本一致
        # 区别：变量解析使用 VariableResolver，支持环境变量 ${env.XXX}
        start_time = time.time()

        from app.services.execution.variable_resolver import VariableResolver
        resolver = VariableResolver()

        url = resolver.resolve(config.get("url", ""), input_variables)
        method = config.get("method", "GET").upper()
        headers = {}
        for k, v in config.get("headers", {}).items():
            headers[k] = resolver.resolve(str(v), input_variables)

        # Auth 处理
        auth = config.get("auth", {})
        if auth.get("type") == "bearer":
            token = resolver.resolve(auth.get("token", ""), input_variables)
            headers["Authorization"] = f"Bearer {token}"
        elif auth.get("type") == "api_key":
            header_name = auth.get("header_name", "X-API-Key")
            key_value = resolver.resolve(auth.get("key_value", ""), input_variables)
            headers[header_name] = key_value

        # SSRF 检查
        ssrf_error = self._check_ssrf(url)
        if ssrf_error:
            return NodeExecutionResult(error=ssrf_error, duration_ms=self._elapsed(start_time))

        # Body 处理
        body_template = config.get("body_template") or config.get("body")
        request_body = resolver.resolve(body_template, input_variables) if body_template else None

        timeout = min(self._resolve_timeout(config), 60)

        try:
            import httpx
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                response = await client.request(
                    method=method, url=url, headers=headers,
                    content=request_body if isinstance(request_body, str) else None,
                    json=request_body if isinstance(request_body, (dict, list)) else None,
                )

            if len(response.content) > self.MAX_RESPONSE_SIZE:
                return NodeExecutionResult(error="Response too large", duration_ms=self._elapsed(start_time))

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
    # _check_ssrf 复用 Phase 4 实现
```

### 4.13 TemplateExecutor（模板转换节点）- Phase 5 扩展

```python
# app/services/node_executors/template_executor.py

class TemplateExecutor(BaseNodeExecutor):
    """
    模板转换节点执行器（工作流执行版本）。
    
    输入/输出定义：
    - 输入：input_mapping 映射的变量
    - 输出：{output_key: 渲染后的文本}
    
    执行逻辑：
    1. 获取 Jinja2 模板字符串
    2. 解析 input_mapping 中的变量
    3. 使用 Jinja2 SandboxEnvironment 渲染
    4. 返回渲染结果
    
    特殊处理：
    - 使用 SandboxEnvironment 防止模板注入攻击
    - 禁止在模板中执行危险操作（如 __class__.__mro__）
    - 模板语法错误时返回明确错误信息
    """

    async def execute(self, config, input_variables, context):
        start_time = time.time()
        template_str = config.get("template", "")
        if not template_str:
            return NodeExecutionResult(error="Template is empty", duration_ms=self._elapsed(start_time))

        from app.services.execution.variable_resolver import VariableResolver
        resolver = VariableResolver()
        input_mapping = config.get("input_mapping", {})
        resolved_vars = {k: resolver.resolve(v, input_variables) for k, v in input_mapping.items()}

        try:
            from jinja2.sandbox import SandboxedEnvironment
            from jinja2 import BaseLoader
            env = SandboxedEnvironment(loader=BaseLoader())
            template = env.from_string(template_str)
            rendered = template.render(**resolved_vars)

            output_key = config.get("output_key", "rendered_text")
            return NodeExecutionResult(output={output_key: rendered}, duration_ms=self._elapsed(start_time))
        except Exception as e:
            return NodeExecutionResult(error=f"Template rendering failed: {str(e)}", duration_ms=self._elapsed(start_time))
```

### 4.14 VariableAggregateExecutor（变量聚合节点）- Phase 5 扩展

```python
# app/services/node_executors/aggregate_executor.py

class VariableAggregateExecutor(BaseNodeExecutor):
    """
    变量聚合节点执行器（工作流执行版本）。
    
    输入/输出定义：
    - 输入：aggregations 中各 sources 的变量引用
    - 输出：{output_key: {聚合名: 聚合结果}}
    
    执行逻辑：
    1. 遍历 aggregations 配置
    2. 对每个聚合项：解析所有 sources 的变量引用
    3. 按 mode 进行聚合：
       - array: 合并为数组 [val1, val2, ...]
       - concat: 字符串拼接 "val1val2..."
       - merge: 字典合并 {**val1, **val2, ...}
       - first: 取第一个非空值
    4. 返回聚合结果
    
    示例：
    {
        "aggregations": [
            {"name": "all_answers", "sources": ["${node_1.result}", "${node_2.result}"], "mode": "array"},
            {"name": "full_text", "sources": ["${node_1.result}", "${node_2.result}"], "mode": "concat"}
        ],
        "output_key": "aggregated"
    }
    """

    async def execute(self, config, input_variables, context):
        start_time = time.time()
        aggregations = config.get("aggregations", [])

        from app.services.execution.variable_resolver import VariableResolver
        resolver = VariableResolver()

        result = {}
        for agg in aggregations:
            name = agg.get("name", "unnamed")
            sources = agg.get("sources", [])
            mode = agg.get("mode", "array")

            values = []
            for src in sources:
                values.append(resolver.resolve(src, input_variables))

            if mode == "array":
                result[name] = values
            elif mode == "concat":
                result[name] = "".join(str(v) for v in values if v is not None)
            elif mode == "merge":
                merged = {}
                for v in values:
                    if isinstance(v, dict):
                        merged.update(v)
                result[name] = merged
            elif mode == "first":
                result[name] = next((v for v in values if v is not None), None)

        output_key = config.get("output_key", "aggregated")
        return NodeExecutionResult(output={output_key: result}, duration_ms=self._elapsed(start_time))
```

### 4.15 ClassifyExecutor（问题分类节点）- Phase 5 扩展

```python
# app/services/node_executors/classify_executor.py

class ClassifyExecutor(BaseNodeExecutor):
    """
    问题分类节点执行器（工作流执行版本）。
    
    输入/输出定义：
    - 输入：input_mapping 映射的待分类文本
    - 输出：{category_id: "cat_1", category_label: "技术问题", confidence: 0.95}
    
    执行逻辑：
    1. 解析待分类文本
    2. 构建分类 Prompt：
       "请对以下文本进行分类。可选类别：
        1. 技术问题 - 描述: ... 关键词: ...
        2. 商务咨询 - 描述: ... 关键词: ...
        3. 其他 - 默认类别
        请返回 JSON: {"category_id": "...", "confidence": 0.0-1.0}"
    3. 调用 LLM（复用 AgentExecutor 的 LLM 调用逻辑）
    4. 解析 LLM 返回的 JSON
    5. 验证 category_id 在预定义类别中
    6. 返回分类结果
    
    特殊处理：
    - LLM 返回非法 JSON 时，选择 is_default=true 的类别
    - category_id 不在预定义列表中时，选择默认类别
    - 调用超时/失败时返回错误
    """

    DEFAULT_TIMEOUT = 60

    async def execute(self, config, input_variables, context):
        start_time = time.time()

        # 解析输入文本
        from app.services.execution.variable_resolver import VariableResolver
        resolver = VariableResolver()
        input_mapping = config.get("input_mapping", {})
        resolved = {k: resolver.resolve(v, input_variables) for k, v in input_mapping.items()}
        text = " ".join(str(v) for v in resolved.values())

        categories = config.get("categories", [])
        if not categories:
            return NodeExecutionResult(error="No categories defined", duration_ms=self._elapsed(start_time))

        # 构建分类 Prompt
        categories_desc = "\n".join([
            f"- {c['id']}: {c.get('label', '')} (关键词: {', '.join(c.get('keywords', []))})"
            for c in categories
        ])
        prompt = f"""请对以下文本进行分类。

可选类别：
{categories_desc}

文本内容：
{text}

请返回 JSON 格式：{{"category_id": "类别ID", "confidence": 0.0到1.0之间的置信度}}"""

        # 调用 LLM
        agent_id = config.get("agent_id")
        if not agent_id:
            return NodeExecutionResult(error="agent_id is required for classification", duration_ms=self._elapsed(start_time))

        try:
            llm_result = await self._call_llm_for_classify(agent_id, prompt, context)
            # 解析结果
            import json
            parsed = json.loads(llm_result)
            category_id = parsed.get("category_id")
            confidence = parsed.get("confidence", 0.0)

            # 验证 category_id
            valid_ids = {c["id"] for c in categories}
            if category_id not in valid_ids:
                # 使用默认类别
                default_cat = next((c for c in categories if c.get("is_default")), categories[-1])
                category_id = default_cat["id"]

            # 获取 label
            category_label = next(
                (c.get("label", "") for c in categories if c["id"] == category_id),
                category_id,
            )

            return NodeExecutionResult(
                output={"category_id": category_id, "category_label": category_label, "confidence": confidence},
                duration_ms=self._elapsed(start_time),
            )
        except (json.JSONDecodeError, Exception) as e:
            # LLM 返回非法结果，使用默认类别
            default_cat = next((c for c in categories if c.get("is_default")), categories[-1] if categories else None)
            if default_cat:
                return NodeExecutionResult(
                    output={"category_id": default_cat["id"], "category_label": default_cat.get("label", ""), "confidence": 0.0},
                    duration_ms=self._elapsed(start_time),
                )
            return NodeExecutionResult(error=f"Classification failed: {str(e)}", duration_ms=self._elapsed(start_time))

    async def _call_llm_for_classify(self, agent_id, prompt, context):
        """复用 AgentExecutor 的 LLM 调用逻辑"""
        # 从 Agent 配置获取模型信息并调用
        # 实现细节与 AgentExecutor 相同
        pass
```

### 4.16 ExtractExecutor（参数提取节点）- Phase 5 扩展

```python
# app/services/node_executors/extract_executor.py

class ExtractExecutor(BaseNodeExecutor):
    """
    参数提取节点执行器（工作流执行版本）。
    
    输入/输出定义：
    - 输入：input_mapping 映射的源文本
    - 输出：{output_key: {参数名: 参数值, ...}}
    
    执行逻辑：
    1. 解析源文本
    2. 构建提取 Prompt：
       "请从以下文本中提取结构化参数。
        提取模式：
        - name (string): 用户姓名
        - email (string): 邮箱地址
        - phone (string): 手机号
        文本：{text}
        请返回 JSON: {"name": "...", "email": "...", "phone": "..."}"
    3. 调用 LLM
    4. 解析 JSON 结果
    5. 按 extraction_schema 验证字段类型
    6. 返回提取结果
    
    特殊处理：
    - LLM 返回非法 JSON 时返回空字典
    - 类型不匹配时尝试自动转换
    - 缺失字段用 null 填充
    """

    DEFAULT_TIMEOUT = 60

    async def execute(self, config, input_variables, context):
        start_time = time.time()

        # 解析输入
        from app.services.execution.variable_resolver import VariableResolver
        resolver = VariableResolver()
        input_mapping = config.get("input_mapping", {})
        resolved = {k: resolver.resolve(v, input_variables) for k, v in input_mapping.items()}
        text = " ".join(str(v) for v in resolved.values())

        extraction_schema = config.get("extraction_schema", [])
        if not extraction_schema:
            return NodeExecutionResult(error="extraction_schema is empty", duration_ms=self._elapsed(start_time))

        # 构建提取 Prompt
        schema_desc = "\n".join([
            f"- {s['name']} ({s.get('type', 'string')}): {s.get('description', '')}"
            for s in extraction_schema
        ])
        prompt = f"""请从以下文本中提取结构化参数。

提取模式：
{schema_desc}

文本内容：
{text}

请返回 JSON 格式，包含上述所有字段。如果某个字段在文本中未找到，请将其设为 null。"""

        # 调用 LLM
        agent_id = config.get("agent_id")
        if not agent_id:
            return NodeExecutionResult(error="agent_id is required", duration_ms=self._elapsed(start_time))

        try:
            llm_result = await self._call_llm_for_extract(agent_id, prompt, context)
            import json
            parsed = json.loads(llm_result)

            # 按 schema 验证和类型转换
            result = {}
            for field in extraction_schema:
                name = field["name"]
                field_type = field.get("type", "string")
                value = parsed.get(name)

                result[name] = self._convert_type(value, field_type)

            output_key = config.get("output_key", "extracted_params")
            return NodeExecutionResult(
                output={output_key: result},
                duration_ms=self._elapsed(start_time),
            )
        except (json.JSONDecodeError, Exception) as e:
            return NodeExecutionResult(error=f"Extraction failed: {str(e)}", duration_ms=self._elapsed(start_time))

    def _convert_type(self, value, target_type):
        """类型转换"""
        if value is None:
            return None
        try:
            if target_type == "string":
                return str(value)
            elif target_type == "number":
                return float(value)
            elif target_type == "integer":
                return int(value)
            elif target_type == "boolean":
                return bool(value)
            elif target_type == "array":
                return list(value) if isinstance(value, list) else [value]
            else:
                return value
        except (ValueError, TypeError):
            return None

    async def _call_llm_for_extract(self, agent_id, prompt, context):
        """复用 AgentExecutor 的 LLM 调用逻辑"""
        pass
```

---

## 5. WebSocket 实现

### 5.1 连接管理

```python
# app/services/execution/ws_broadcaster.py

import asyncio
import json
import structlog
from typing import Any
from fastapi import WebSocket, WebSocketDisconnect

logger = structlog.get_logger()


class ConnectionManager:
    """
    WebSocket 连接管理器。
    
    管理每个执行ID对应的所有 WebSocket 连接。
    一个执行可以有多个客户端连接（多标签页/多设备）。
    """

    def __init__(self):
        # execution_id -> set of WebSocket connections
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, execution_id: str, websocket: WebSocket):
        """接受并注册新的 WebSocket 连接"""
        await websocket.accept()
        async with self._lock:
            if execution_id not in self._connections:
                self._connections[execution_id] = set()
            self._connections[execution_id].add(websocket)
        logger.info("ws_connected", execution_id=execution_id)

    async def disconnect(self, execution_id: str, websocket: WebSocket):
        """移除断开的连接"""
        async with self._lock:
            if execution_id in self._connections:
                self._connections[execution_id].discard(websocket)
                if not self._connections[execution_id]:
                    del self._connections[execution_id]
        logger.info("ws_disconnected", execution_id=execution_id)

    async def broadcast(self, execution_id: str, message: dict[str, Any]):
        """
        向某个执行的所有连接广播消息。
        
        消息自动序列化为 JSON。
        发送失败的连接会被自动移除。
        """
        async with self._lock:
            connections = self._connections.get(execution_id, set()).copy()

        if not connections:
            return

        message_json = json.dumps(message, ensure_ascii=False, default=str)
        dead_connections = []

        for ws in connections:
            try:
                await ws.send_text(message_json)
            except Exception:
                dead_connections.append(ws)

        # 清理断开的连接
        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    if execution_id in self._connections:
                        self._connections[execution_id].discard(ws)

    def get_connection_count(self, execution_id: str) -> int:
        """获取某个执行的连接数"""
        return len(self._connections.get(execution_id, set()))


# 全局单例
ws_manager = ConnectionManager()
```

### 5.2 WebSocket 路由

```python
# app/api/v1/ws.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from app.services.execution.ws_broadcaster import ws_manager
from app.core.security import decode_token

router = APIRouter()


@router.websocket("/api/executions/{execution_id}/stream")
async def execution_stream(
    websocket: WebSocket,
    execution_id: str,
    token: str = Query(..., description="JWT access token"),
):
    """
    WebSocket 实时推送工作流执行状态。
    
    连接参数：
    - execution_id: 执行记录 ID（路径参数）
    - token: JWT access_token（查询参数）
    
    连接流程：
    1. 验证 JWT token
    2. 验证 execution 存在且属于当前用户
    3. 接受连接
    4. 发送当前执行状态快照（断连重连时恢复状态）
    5. 持续推送实时消息
    
    下行消息类型：
    - node_status_change: 节点状态变更
    - log: 实时日志
    - execution_status: 执行状态变更
    - review_request: 审核请求
    - error: 错误消息
    
    上行消息类型：
    - ping: 心跳
    - review_action: 审核操作（通过 HTTP API 更推荐）
    """
    # 1. 验证 Token
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=4001, reason="Invalid token")
            return
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # 2. 验证执行记录（需要数据库查询）
    # 简化处理：在路由层验证，具体逻辑在依赖注入中

    # 3. 连接
    await ws_manager.connect(execution_id, websocket)

    try:
        # 4. 发送当前状态快照
        # （从 Redis 或数据库获取当前执行状态）
        await ws_manager.broadcast(execution_id, {
            "type": "connected",
            "execution_id": execution_id,
            "message": "已连接到执行流",
        })

        # 5. 持续监听客户端消息
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type")

                if msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                # 其他上行消息通过 HTTP API 处理更合适

            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "code": "INVALID_MESSAGE",
                    "message": "Invalid JSON message",
                }))

    except WebSocketDisconnect:
        await ws_manager.disconnect(execution_id, websocket)
    except Exception as e:
        logger.error("ws_error", execution_id=execution_id, error=str(e))
        await ws_manager.disconnect(execution_id, websocket)
```

### 5.3 消息格式定义

```python
# app/schemas/websocket.py — Phase 5 完整定义

from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


# ==================== 下行消息（服务端 → 客户端） ====================

class WSNodeStatusChange(BaseModel):
    """节点状态变更"""
    type: str = "node_status_change"
    node_id: str
    status: str              # pending | running | success | failed | skipped | paused
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    output: Optional[Any] = None
    duration_ms: Optional[int] = None
    tokens_used: Optional[int] = None
    error: Optional[str] = None


class WSLogMessage(BaseModel):
    """实时日志"""
    type: str = "log"
    level: str               # info | warn | error
    message: str
    node_id: Optional[str] = None
    timestamp: str


class WSExecutionStatus(BaseModel):
    """执行状态变更"""
    type: str = "execution_status"
    status: str              # running | success | failed | paused | cancelled
    total_duration_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    output: Optional[dict] = None
    error: Optional[str] = None


class WSReviewRequest(BaseModel):
    """审核请求"""
    type: str = "review_request"
    node_id: str
    input_data: Optional[dict] = None


class WSErrorMessage(BaseModel):
    """错误消息"""
    type: str = "error"
    node_id: Optional[str] = None
    error_message: str
    code: Optional[str] = None


class WSConnectedMessage(BaseModel):
    """连接成功消息"""
    type: str = "connected"
    execution_id: str
    message: str


# ==================== 上行消息（客户端 → 服务端） ====================

class WSPingMessage(BaseModel):
    """心跳"""
    type: str = "ping"
```

### 5.4 断连处理

```
断连处理策略：

1. 客户端断连：
   - ConnectionManager 自动移除断开的连接
   - 不影响工作流执行（工作流在后台继续执行）
   - 客户端重连后可以重新建立连接

2. 重连恢复：
   - 客户端重连时，服务端发送当前执行状态快照
   - 包含已完成节点的输出和当前节点的状态
   - 客户端根据快照恢复 UI 显示

3. 服务端断连：
   - 工作流执行不受 WebSocket 连接影响
   - 执行引擎独立于 WebSocket 运行
   - 客户端重连后可以继续接收后续消息

4. 心跳机制：
   - 客户端每 30 秒发送 {"type": "ping"}
   - 服务端回复 {"type": "pong"}
   - 60 秒无心跳视为断连
```

---

## 6. 审核节点完整流程

### 6.1 流程概览

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│ 审核节点  │ ──→ │ 暂停工作流   │ ──→ │ WebSocket    │ ──→ │ 等待审核  │
│ 开始执行  │     │ 状态=paused  │     │ 广播审核请求  │     │ 结果     │
└──────────┘     └──────────────┘     └──────────────┘     └────┬─────┘
                                                                 │
                    ┌──────────────┐     ┌──────────────┐        │
                    │ 继续执行     │ ←── │ 恢复工作流   │ ←──────┘
                    │ 后续节点     │     │ 状态=running │     POST /review
                    └──────────────┘     └──────────────┘
```

### 6.2 ReviewManager 实现

```python
# app/services/execution/review_manager.py

import asyncio
import json
import structlog
from typing import Any, Optional
from datetime import datetime, timezone

logger = structlog.get_logger()


class ReviewManager:
    """
    审核管理器。
    
    负责：
    1. 管理审核暂停的执行
    2. 通过 Redis 存储和获取审核结果
    3. 通过 asyncio.Event 通知等待的协程
    
    使用 Redis 作为信号通道：
    - Key: review:{execution_id}:{node_id}
    - Value: 审核结果 JSON
    - Pub/Sub: 审核结果发布后通知等待者
    """

    def __init__(self, redis):
        self.redis = redis
        self._events: dict[str, asyncio.Event] = {}

    async def wait_for_review(
        self,
        execution_id,
        node_id: str,
        timeout: int = 3600,
    ) -> dict[str, Any]:
        """
        等待审核结果。
        
        使用 Redis Pub/Sub 监听审核结果：
        1. 订阅 channel: review:{execution_id}
        2. 等待消息或超时
        3. 收到消息后验证 node_id 匹配
        4. 返回审核结果
        """
        channel = f"review:{execution_id}"
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)

        try:
            # 等待消息
            async with asyncio.timeout(timeout):
                while True:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )
                    if message and message["type"] == "message":
                        data = json.loads(message["data"])
                        if data.get("node_id") == node_id:
                            return data
                    await asyncio.sleep(0.1)

        except asyncio.TimeoutError:
            return {"action": "timeout", "comment": "审核超时"}
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    async def submit_review(
        self,
        execution_id,
        node_id: str,
        action: str,
        comment: Optional[str] = None,
        modified_data: Optional[dict] = None,
    ):
        """
        提交审核结果。
        
        通过 Redis Pub/Sub 发布审核结果：
        1. 构建审核结果 JSON
        2. 发布到 channel: review:{execution_id}
        3. 等待中的 WorkflowExecutor 会收到消息
        """
        channel = f"review:{execution_id}"
        result = {
            "node_id": node_id,
            "action": action,
            "comment": comment,
            "modified_data": modified_data,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.redis.publish(channel, json.dumps(result, ensure_ascii=False))
        logger.info("review_submitted", execution_id=str(execution_id), node_id=node_id, action=action)
```

### 6.3 审核 API 路由

```python
# app/api/v1/executions.py 中的审核路由

@router.post("/api/executions/{execution_id}/nodes/{node_id}/review")
async def submit_review(
    execution_id: uuid.UUID,
    node_id: str,
    request: ReviewActionRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """
    提交审核操作。
    
    请求体：
    {
        "action": "approve" | "reject" | "modify",
        "modified_data": {...},  // 仅 modify 时
        "comment": "审核意见"
    }
    
    业务逻辑：
    1. 验证执行记录存在且属于当前用户
    2. 验证执行状态为 paused
    3. 验证节点为审核节点
    4. 通过 ReviewManager 发布审核结果
    5. 后台任务恢复工作流执行
    
    注意：审核提交后，工作流恢复执行是异步的。
    API 立即返回 200，工作流在后台继续执行。
    """
    # 1. 验证执行记录
    execution = await db.get(Execution, execution_id)
    if not execution:
        raise AppException(404, "EXECUTION_NOT_FOUND", "执行记录不存在")

    # 验证权限
    workflow = await db.get(Workflow, execution.workflow_id)
    if workflow.user_id != current_user.id:
        raise AppException(403, "FORBIDDEN", "无权操作")

    # 2. 验证状态
    if execution.status != ExecutionStatus.paused:
        raise AppException(400, "EXECUTION_NOT_PAUSED", "执行未在暂停状态")

    # 3. 验证节点
    exec_node = await db.execute(
        select(ExecutionNode).where(
            ExecutionNode.execution_id == execution_id,
            ExecutionNode.node_id == node_id,
        )
    )
    exec_node = exec_node.scalar_one_or_none()
    if not exec_node or exec_node.node_type != "reviewNode":
        raise AppException(400, "INVALID_REVIEW_NODE", "无效的审核节点")

    # 4. 发布审核结果
    review_mgr = ReviewManager(redis)
    await review_mgr.submit_review(
        execution_id=execution_id,
        node_id=node_id,
        action=request.action,
        comment=request.comment,
        modified_data=request.modified_data,
    )

    # 5. 更新执行状态为 running（恢复执行）
    execution.status = ExecutionStatus.running
    exec_node.status = NodeStatus.success
    exec_node.output_data = {
        "review_action": request.action,
        "review_comment": request.comment,
    }
    if request.modified_data:
        exec_node.output_data["modified_data"] = request.modified_data
    exec_node.finished_at = datetime.now(timezone.utc)
    await db.flush()

    # 6. 启动后台任务恢复执行
    # 实际实现中，这里需要重新启动 WorkflowExecutor 从暂停点继续
    # 简化处理：通过 Redis 发布恢复信号
    await redis.publish(f"resume:{execution_id}", json.dumps({"node_id": node_id}))

    return ReviewActionResponse(
        execution_id=execution_id,
        node_id=node_id,
        action=request.action,
    )
```

### 6.4 审核数据结构

```json
// 审核请求（WebSocket 下行）
{
    "type": "review_request",
    "node_id": "node_review_1",
    "input_data": {
        "agent_result": "AI 生成的代码内容...",
        "query": "用户原始问题"
    }
}

// 审核操作（HTTP POST）
{
    "action": "approve",           // "approve" | "reject" | "modify"
    "comment": "代码质量良好，可以通过",
    "modified_data": null          // action="modify" 时提供修改后的数据
}

// 审核操作响应
{
    "execution_id": "uuid",
    "node_id": "node_review_1",
    "action": "approve",
    "message": "审核操作已处理"
}
```

---

## 7. 执行记录与日志

### 7.1 执行记录生命周期

```
创建 Execution (status=pending)
    ↓
启动执行 (status=running)
    ↓
┌─── 逐节点执行 ───────────────────────────────┐
│  创建 ExecutionNode (status=running)          │
│      ↓                                        │
│  节点执行成功 → status=success                │
│  节点执行失败 → status=failed                 │
│  节点被跳过   → status=skipped                │
│  节点等待审核 → status=paused                 │
└───────────────────────────────────────────────┘
    ↓
执行完成 → status=success, output_data=最终输出
执行失败 → status=failed, 记录错误信息
执行取消 → status=cancelled
执行暂停 → status=paused（等待审核恢复）
```

### 7.2 ExecutionService 实现

```python
# app/services/execution_service.py

import uuid
import asyncio
import structlog
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import Execution, ExecutionNode, Log
from app.models.workflow import Workflow
from app.models.enums import ExecutionStatus
from app.schemas.execution import (
    ExecutionListItem,
    ExecutionListResponse,
    ExecutionDetailResponse,
    ExecutionNodeDetail,
    CancelExecutionResponse,
)
from app.services.execution.executor import WorkflowExecutor
from app.services.execution.ws_broadcaster import ws_manager
from app.services.execution.cancellation import CancellationManager
from app.services.execution.review_manager import ReviewManager

logger = structlog.get_logger()


class ExecutionService:
    """执行管理服务"""

    def __init__(self, db: AsyncSession, redis):
        self.db = db
        self.redis = redis

    async def start_execution(
        self,
        workflow_id: uuid.UUID,
        user_id: uuid.UUID,
        input_data: dict,
    ) -> Execution:
        """
        启动工作流执行。
        
        步骤：
        1. 查询工作流 + 权限检查
        2. 使用当前版本的 nodes_data/edges_data
        3. 创建 Execution 记录
        4. 在后台任务中启动 WorkflowExecutor
        5. 返回 Execution 信息
        """
        # 1. 查询工作流
        workflow = await self.db.get(Workflow, workflow_id)
        if not workflow:
            raise ValueError("Workflow not found")
        if workflow.user_id != user_id:
            raise PermissionError("Forbidden")

        if not workflow.nodes_data or not workflow.edges_data:
            raise ValueError("Workflow has no nodes or edges")

        # 2. 创建执行记录
        execution = Execution(
            id=uuid.uuid4(),
            workflow_id=workflow_id,
            version_number=workflow.current_version,
            status=ExecutionStatus.pending,
            input_data=input_data,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(execution)
        await self.db.flush()

        # 3. 在后台启动执行
        executor = WorkflowExecutor(
            db=self.db,
            redis=self.redis,
            broadcaster=ws_manager,
            cancellation_mgr=CancellationManager(self.redis),
            review_mgr=ReviewManager(self.redis),
        )

        # 使用 asyncio.create_task 在后台执行
        asyncio.create_task(
            self._run_execution(
                executor, execution,
                workflow.nodes_data, workflow.edges_data,
                input_data, user_id,
            )
        )

        return execution

    async def _run_execution(
        self,
        executor: WorkflowExecutor,
        execution: Execution,
        nodes_data: list,
        edges_data: list,
        input_data: dict,
        user_id: uuid.UUID,
    ):
        """后台执行工作流"""
        try:
            await executor.execute(execution, nodes_data, edges_data, input_data, user_id)
        except Exception as e:
            logger.error("execution_background_error", error=str(e))
        finally:
            await self.db.commit()

    async def cancel_execution(
        self,
        execution_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> CancelExecutionResponse:
        """
        取消执行。
        
        步骤：
        1. 查询执行记录 + 权限检查
        2. 验证状态为 running 或 paused
        3. 设置取消标志（Redis）
        4. 当前节点执行完后停止后续节点
        """
        execution = await self.db.get(Execution, execution_id)
        if not execution:
            raise ValueError("Execution not found")

        workflow = await self.db.get(Workflow, execution.workflow_id)
        if workflow.user_id != user_id:
            raise PermissionError("Forbidden")

        if execution.status not in (ExecutionStatus.running, ExecutionStatus.paused):
            raise ValueError(f"Cannot cancel execution in {execution.status} status")

        # 设置取消标志
        cancellation_mgr = CancellationManager(self.redis)
        await cancellation_mgr.set_cancelled(execution_id)

        # 如果暂停状态，也需要恢复执行让它能检查取消标志
        if execution.status == ExecutionStatus.paused:
            await self.redis.publish(f"resume:{execution_id}", "{}")

        return CancelExecutionResponse(execution_id=execution_id)

    async def list_executions(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        workflow_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
    ) -> ExecutionListResponse:
        """
        获取执行历史列表。
        
        支持筛选：
        - workflow_id: 按工作流筛选
        - status: 按状态筛选
        """
        # 构建查询
        query = (
            select(Execution)
            .join(Workflow)
            .where(Workflow.user_id == user_id)
        )

        if workflow_id:
            query = query.where(Execution.workflow_id == workflow_id)
        if status:
            query = query.where(Execution.status == status)

        # 总数
        count_query = select(func.count(Execution.id)).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar()

        # 分页
        offset = (page - 1) * page_size
        query = query.order_by(Execution.started_at.desc()).offset(offset).limit(page_size)
        result = await self.db.execute(query)
        executions = result.scalars().all()

        items = []
        for e in executions:
            wf = await self.db.get(Workflow, e.workflow_id)
            items.append(ExecutionListItem(
                id=e.id,
                workflow_id=e.workflow_id,
                workflow_name=wf.name if wf else None,
                version_number=e.version_number,
                status=e.status.value,
                total_duration_ms=e.total_duration_ms,
                total_tokens=e.total_tokens,
                started_at=e.started_at,
                finished_at=e.finished_at,
            ))

        return ExecutionListResponse(
            items=items,
            total=total or 0,
            page=page,
            page_size=page_size,
            has_next=(offset + page_size) < (total or 0),
        )

    async def get_execution_detail(
        self,
        execution_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ExecutionDetailResponse:
        """
        获取执行详情（含所有节点记录）。
        """
        execution = await self.db.get(Execution, execution_id)
        if not execution:
            raise ValueError("Execution not found")

        workflow = await self.db.get(Workflow, execution.workflow_id)
        if workflow.user_id != user_id:
            raise PermissionError("Forbidden")

        # 查询节点记录
        nodes_result = await self.db.execute(
            select(ExecutionNode)
            .where(ExecutionNode.execution_id == execution_id)
            .order_by(ExecutionNode.started_at)
        )
        exec_nodes = nodes_result.scalars().all()

        node_details = []
        for n in exec_nodes:
            node_details.append(ExecutionNodeDetail(
                id=n.id,
                execution_id=n.execution_id,
                node_id=n.node_id,
                node_type=n.node_type,
                status=n.status.value,
                input_data=n.input_data,
                output_data=n.output_data,
                duration_ms=n.duration_ms,
                tokens_used=n.tokens_used,
                error_message=n.error_message,
                started_at=n.started_at,
                finished_at=n.finished_at,
            ))

        return ExecutionDetailResponse(
            id=execution.id,
            workflow_id=execution.workflow_id,
            workflow_name=workflow.name if workflow else None,
            version_number=execution.version_number,
            status=execution.status.value,
            input_data=execution.input_data,
            output_data=execution.output_data,
            total_duration_ms=execution.total_duration_ms,
            total_tokens=execution.total_tokens,
            total_cost=execution.total_cost,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
            nodes=node_details,
        )
```

### 7.3 LogService 实现

```python
# app/services/log_service.py

import uuid
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import Log
from app.models.workflow import Workflow, Execution
from app.schemas.execution import LogListResponse, LogDetailResponse, LogListParams


class LogService:
    """日志服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_logs(
        self,
        user_id: uuid.UUID,
        params: LogListParams,
    ) -> LogListResponse:
        """
        获取日志列表。
        
        支持筛选：
        - execution_id: 按执行记录筛选
        - node_id: 按节点筛选
        - level: 按日志级别筛选
        
        注意：需要验证用户权限（通过 execution → workflow → user_id）
        """
        query = select(Log)

        # 如果按 execution_id 筛选，需要验证权限
        if params.execution_id:
            execution = await self.db.get(Execution, params.execution_id)
            if not execution:
                raise ValueError("Execution not found")
            workflow = await self.db.get(Workflow, execution.workflow_id)
            if workflow.user_id != user_id:
                raise PermissionError("Forbidden")
            query = query.where(Log.execution_id == params.execution_id)

        if params.node_id:
            query = query.where(Log.node_id == params.node_id)
        if params.level:
            query = query.where(Log.level == params.level)

        # 总数
        count_query = select(func.count(Log.id)).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar()

        # 分页
        offset = (params.page - 1) * params.page_size
        query = query.order_by(Log.timestamp.desc()).offset(offset).limit(params.page_size)
        result = await self.db.execute(query)
        logs = result.scalars().all()

        items = [LogDetailResponse.model_validate(log) for log in logs]

        return LogListResponse(
            items=items,
            total=total or 0,
            page=params.page,
            page_size=params.page_size,
            has_next=(offset + params.page_size) < (total or 0),
        )

    async def get_log_detail(
        self,
        log_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> LogDetailResponse:
        """获取日志详情"""
        log = await self.db.get(Log, log_id)
        if not log:
            raise ValueError("Log not found")

        # 权限验证
        execution = await self.db.get(Execution, log.execution_id)
        workflow = await self.db.get(Workflow, execution.workflow_id)
        if workflow.user_id != user_id:
            raise PermissionError("Forbidden")

        return LogDetailResponse.model_validate(log)
```

---

## 8. 每个 API 完整规格

### 8.0 通用约定

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

- 用户只能操作自己的执行记录和日志
- 通过 execution → workflow → user_id 链路验证

---

### 8.1 启动执行

**`POST /api/workflows/:id/run`**

**描述**：启动工作流执行。

**路径参数**：
- `id` (uuid): 工作流 ID

**请求体**：`WorkflowRunRequest`

```json
{
  "input_data": {
    "user_query": "帮我写一个 React 组件",
    "language": "TypeScript"
  }
}
```

**业务逻辑**（`ExecutionService.start_execution`）：

1. 查询工作流 + 权限检查（workflow.user_id == current_user.id）
2. 工作流不存在 → 404 `WORKFLOW_NOT_FOUND`
3. 权限不足 → 403 `FORBIDDEN`
4. 工作流无节点/边数据 → 400 `WORKFLOW_EMPTY`
5. 创建 Execution 记录（status=pending）
6. 使用 `asyncio.create_task` 在后台启动 `WorkflowExecutor.execute()`
7. 立即返回 execution_id

**响应体**：`WorkflowRunResponse`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "execution_id": "uuid",
    "status": "running",
    "message": "工作流已开始执行"
  }
}
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `WORKFLOW_NOT_FOUND` | 工作流不存在 |
| 403 | `FORBIDDEN` | 无权执行 |
| 400 | `WORKFLOW_EMPTY` | 工作流无节点数据 |
| 401 | `UNAUTHORIZED` | 未登录 |

---

### 8.2 取消执行

**`POST /api/executions/:id/cancel`**

**描述**：取消正在执行的工作流。

**业务逻辑**（`ExecutionService.cancel_execution`）：

1. 查询执行记录 + 权限检查
2. 验证状态为 running 或 paused
3. 通过 CancellationManager 在 Redis 设置取消标志
4. 当前节点执行完后停止后续节点
5. 更新执行状态为 cancelled

**响应体**：`CancelExecutionResponse`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "execution_id": "uuid",
    "status": "cancelled",
    "message": "执行已取消"
  }
}
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `EXECUTION_NOT_FOUND` | 执行记录不存在 |
| 400 | `EXECUTION_NOT_CANCELLABLE` | 当前状态不可取消 |

---

### 8.3 执行历史列表

**`GET /api/executions`**

**描述**：获取当前用户的执行历史列表。

**查询参数**：

```
page: int (default=1)
page_size: int (default=20, max=100)
workflow_id: uuid (可选, 按工作流筛选)
status: string (可选, 按状态筛选: pending|running|success|failed|paused|cancelled)
```

**响应体**：`ExecutionListResponse`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "uuid",
        "workflow_id": "uuid",
        "workflow_name": "代码审查流水线",
        "version_number": 3,
        "status": "success",
        "total_duration_ms": 15230,
        "total_tokens": 4521,
        "started_at": "2026-07-20T10:30:00Z",
        "finished_at": "2026-07-20T10:30:15Z"
      }
    ],
    "total": 42,
    "page": 1,
    "page_size": 20,
    "has_next": true
  }
}
```

---

### 8.4 执行详情

**`GET /api/executions/:id`**

**描述**：获取执行详情，包含所有节点执行记录。

**响应体**：`ExecutionDetailResponse`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": "uuid",
    "workflow_id": "uuid",
    "workflow_name": "代码审查流水线",
    "version_number": 3,
    "status": "success",
    "input_data": {"user_query": "..."},
    "output_data": {"final_answer": "..."},
    "total_duration_ms": 15230,
    "total_tokens": 4521,
    "total_cost": 0.023456,
    "started_at": "2026-07-20T10:30:00Z",
    "finished_at": "2026-07-20T10:30:15Z",
    "nodes": [
      {
        "id": "uuid",
        "execution_id": "uuid",
        "node_id": "node_start_1",
        "node_type": "startNode",
        "status": "success",
        "input_data": null,
        "output_data": {"user_query": "..."},
        "duration_ms": 5,
        "tokens_used": null,
        "error_message": null,
        "started_at": "2026-07-20T10:30:00Z",
        "finished_at": "2026-07-20T10:30:00Z"
      }
    ]
  }
}
```

---

### 8.5 审核操作

**`POST /api/executions/:execution_id/nodes/:node_id/review`**

**描述**：提交审核节点的操作。

**请求体**：`ReviewActionRequest`

```json
{
  "action": "approve",
  "comment": "代码质量良好",
  "modified_data": null
}
```

**业务逻辑**：

1. 验证执行记录存在且属于当前用户
2. 验证执行状态为 paused
3. 验证目标节点为审核节点且状态为 paused
4. 通过 ReviewManager 发布审核结果（Redis Pub/Sub）
5. 更新 ExecutionNode 状态为 success
6. 恢复执行状态为 running
7. 后台任务从暂停点继续执行

**响应体**：`ReviewActionResponse`

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `EXECUTION_NOT_FOUND` | 执行记录不存在 |
| 400 | `EXECUTION_NOT_PAUSED` | 执行未在暂停状态 |
| 400 | `INVALID_REVIEW_NODE` | 无效的审核节点 |

---

### 8.6 WebSocket 实时推送

**`WS /api/executions/:id/stream?token=xxx`**

详见第 5 章。

---

### 8.7 日志列表

**`GET /api/logs`**

**描述**：获取日志列表，支持筛选。

**查询参数**：

```
page: int (default=1)
page_size: int (default=20, max=100)
execution_id: uuid (可选)
node_id: string (可选)
level: string (可选: info|warn|error)
```

**响应体**：`LogListResponse`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "uuid",
        "execution_id": "uuid",
        "node_id": "node_agent_1",
        "level": "info",
        "message": "开始执行节点: Agent 节点 (agentNode)",
        "timestamp": "2026-07-20T10:30:05Z"
      }
    ],
    "total": 156,
    "page": 1,
    "page_size": 20,
    "has_next": true
  }
}
```

---

### 8.8 日志详情

**`GET /api/logs/:id`**

**描述**：获取单条日志详情。

**响应体**：`LogDetailResponse`

---

## 9. Service 层架构

### 9.1 服务分层

```
API Layer (路由层)
    ↓ 调用
Service Layer (业务逻辑层)
    ├── ExecutionService    # 执行管理（启动/取消/查询）
    ├── WorkflowExecutor    # 执行引擎核心（编排逻辑）
    ├── LogService          # 日志管理
    ├── NodeExecutorRegistry # 节点执行器注册表
    └── ReviewManager       # 审核管理
    ↓ 调用
Infrastructure Layer (基础设施层)
    ├── ExecutionContext     # 执行上下文
    ├── TopoSorter          # 拓扑排序
    ├── VariableResolver    # 变量解析
    ├── WSBroadcaster       # WebSocket 广播
    ├── CancellationManager # 取消管理
    └── 16 个 NodeExecutor  # 节点执行器
    ↓ 调用
Persistence Layer (持久化层)
    ├── Execution (SQLAlchemy Model)
    ├── ExecutionNode (SQLAlchemy Model)
    ├── Log (SQLAlchemy Model)
    ├── Redis (缓存/消息)
    └── External APIs (LLM/Embedding/HTTP)
```

### 9.2 依赖注入

```python
# app/api/deps.py — Phase 5 新增依赖

from app.services.execution_service import ExecutionService
from app.services.log_service import LogService
from app.services.execution.ws_broadcaster import ws_manager
from app.services.execution.cancellation import CancellationManager
from app.services.execution.review_manager import ReviewManager


async def get_execution_service(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> ExecutionService:
    return ExecutionService(db=db, redis=redis)


async def get_log_service(
    db: AsyncSession = Depends(get_db),
) -> LogService:
    return LogService(db=db)


def get_ws_broadcaster() -> WSBroadcaster:
    return ws_manager


async def get_cancellation_manager(
    redis=Depends(get_redis),
) -> CancellationManager:
    return CancellationManager(redis=redis)


async def get_review_manager(
    redis=Depends(get_redis),
) -> ReviewManager:
    return ReviewManager(redis=redis)
```

---

## 10. 错误码

### 10.1 执行相关错误码

| 错误码 | HTTP 状态码 | 说明 |
|--------|-----------|------|
| `EXECUTION_NOT_FOUND` | 404 | 执行记录不存在 |
| `EXECUTION_NOT_CANCELLABLE` | 400 | 当前状态不可取消 |
| `EXECUTION_NOT_PAUSED` | 400 | 执行未在暂停状态 |
| `WORKFLOW_EMPTY` | 400 | 工作流无节点/边数据 |
| `WORKFLOW_NOT_FOUND` | 404 | 工作流不存在 |
| `FORBIDDEN` | 403 | 无权操作 |
| `UNAUTHORIZED` | 401 | 未登录 |
| `INVALID_REVIEW_NODE` | 400 | 无效的审核节点 |
| `REVIEW_TIMEOUT` | 408 | 审核超时 |

### 10.2 节点执行错误码

| 错误码 | 说明 |
|--------|------|
| `NODE_EXECUTION_FAILED` | 节点执行失败 |
| `NODE_EXECUTION_TIMEOUT` | 节点执行超时 |
| `MISSING_REQUIRED_INPUT` | 缺少必填输入参数 |
| `AGENT_NOT_FOUND` | Agent 不存在 |
| `MODEL_NOT_CONFIGURED` | 模型未配置 |
| `LLM_API_ERROR` | LLM API 调用失败 |
| `KB_NOT_FOUND` | 知识库不存在 |
| `EMBEDDING_FAILED` | 向量化失败 |
| `CODE_SECURITY_VIOLATION` | 代码安全检查失败 |
| `CODE_EXECUTION_TIMEOUT` | 代码执行超时 |
| `SSRF_BLOCKED` | SSRF 防护拦截 |
| `HTTP_REQUEST_FAILED` | HTTP 请求失败 |
| `TEMPLATE_RENDER_FAILED` | 模板渲染失败 |
| `CLASSIFICATION_FAILED` | 分类失败 |
| `EXTRACTION_FAILED` | 参数提取失败 |
| `LOOP_NOT_ARRAY` | 循环变量不是数组 |
| `TEST_ASSERTION_FAILED` | 测试断言失败 |

### 10.3 WebSocket 错误码

| 错误码 | 说明 |
|--------|------|
| `WS_INVALID_TOKEN` | 无效的 JWT Token |
| `WS_EXECUTION_NOT_FOUND` | 执行记录不存在 |
| `WS_INVALID_MESSAGE` | 无效的消息格式 |

---

## 11. 与 Phase 0-4 的衔接

### 11.1 复用 Phase 0 的内容

| 组件 | Phase 0 定义 | Phase 5 使用方式 |
|------|-------------|-----------------|
| Execution 模型 | `app/models/execution.py` | 直接复用，创建/更新执行记录 |
| ExecutionNode 模型 | `app/models/execution.py` | 直接复用，记录每个节点的执行 |
| Log 模型 | `app/models/execution.py` | 直接复用，记录执行日志 |
| ExecutionStatus 枚举 | `app/models/enums.py` | 直接使用 |
| NodeStatus 枚举 | `app/models/enums.py` | 直接使用 |
| LogLevel 枚举 | `app/models/enums.py` | 直接使用 |
| 数据库连接 | `app/core/database.py` | 直接使用 AsyncSession |
| Redis 连接 | `app/core/redis.py` | 直接使用 Redis 客户端 |
| 异常处理 | `app/core/exceptions.py` | 直接使用 AppException |

### 11.2 复用 Phase 2 的内容

| 组件 | Phase 2 定义 | Phase 5 使用方式 |
|------|-------------|-----------------|
| Agent 模型 | `app/models/agent.py` | 查询 Agent 配置（model, prompt 等） |
| ModelProvider 模型 | `app/models/model_provider.py` | 查询 API Key、调用 LLM |
| ModelUsage 模型 | `app/models/model_provider.py` | 记录 Token 消耗 |
| LLM 调用逻辑 | Phase 2 AgentExecutor | 复用 `_call_llm` 方法 |
| 加密/解密 | `app/core/encryption.py` | 解密 API Key |

### 11.3 复用 Phase 3 的内容

| 组件 | Phase 3 定义 | Phase 5 使用方式 |
|------|-------------|-----------------|
| KnowledgeBase 模型 | `app/models/knowledge.py` | 查询知识库配置 |
| KnowledgeChunk 模型 | `app/models/knowledge.py` | pgvector 向量检索 |
| Embedding 调用 | Phase 3 服务 | 复用 Embedding API |

### 11.4 复用 Phase 4 的内容

| 组件 | Phase 4 定义 | Phase 5 使用方式 |
|------|-------------|-----------------|
| Workflow 模型 | `app/models/workflow.py` | 获取 nodes_data/edges_data |
| NodeType 枚举 | `app/models/enums.py` | 判断节点类型 |
| BaseNodeExecutor | `app/services/node_executors/base.py` | 扩展为工作流版本 |
| NodeExecutorRegistry | `app/services/node_executors/registry.py` | 注册全部 16 种执行器 |
| 各 NodeExecutor | Phase 4 实现 | 每个都扩展为工作流版本 |
| VariableResolver | 在 `_resolve_variables` 中 | 抽取为独立类 |
| WebSocket Schema | `app/schemas/websocket.py` | Phase 4 定义，Phase 5 实现 |

### 11.5 Phase 5 新增内容

| 新增 | 文件路径 | 说明 |
|------|---------|------|
| WorkflowExecutor | `app/services/execution/executor.py` | 执行引擎核心 |
| ExecutionContext | `app/services/execution/context.py` | 执行上下文管理 |
| TopoSorter | `app/services/execution/topo_sorter.py` | 拓扑排序 |
| VariableResolver | `app/services/execution/variable_resolver.py` | 独立变量解析引擎 |
| WSBroadcaster | `app/services/execution/ws_broadcaster.py` | WebSocket 广播 |
| CancellationManager | `app/services/execution/cancellation.py` | 取消管理 |
| ReviewManager | `app/services/execution/review_manager.py` | 审核管理 |
| ExecutionService | `app/services/execution_service.py` | 执行管理 Service |
| LogService | `app/services/log_service.py` | 日志 Service |
| StartExecutor | `app/services/node_executors/start_executor.py` | 新增 |
| EndExecutor | `app/services/node_executors/end_executor.py` | 新增 |
| ReviewExecutor | `app/services/node_executors/review_executor.py` | 新增 |
| TestExecutor | `app/services/node_executors/test_executor.py` | 新增 |
| WS 路由 | `app/api/v1/ws.py` | 新增 |

---

## 12. 测试用例

### 12.1 执行引擎单元测试

```python
# tests/test_execution/test_executor.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.execution.executor import WorkflowExecutor
from app.services.execution.context import ExecutionContext


class TestWorkflowExecutor:
    """执行引擎测试"""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    @pytest.fixture
    def executor(self, mock_db, mock_redis):
        return WorkflowExecutor(
            db=mock_db,
            redis=mock_redis,
            broadcaster=AsyncMock(),
            cancellation_mgr=AsyncMock(),
            review_mgr=AsyncMock(),
        )

    async def test_simple_linear_workflow(self, executor, mock_db):
        """测试简单线性工作流：开始 → Agent → 结束"""
        # 准备数据
        nodes = [
            {"id": "start", "type": "startNode", "data": {"inputs": [{"name": "query", "type": "string", "required": True}]}},
            {"id": "agent", "type": "agentNode", "data": {"agent_id": "uuid", "input_mapping": {"q": "${start.query}"}}},
            {"id": "end", "type": "endNode", "data": {"output_mapping": {"answer": "${agent.result}"}}},
        ]
        edges = [
            {"id": "e1", "source": "start", "target": "agent"},
            {"id": "e2", "source": "agent", "target": "end"},
        ]
        input_data = {"query": "hello"}

        # 执行
        execution = MagicMock()
        execution.id = "exec-1"
        execution.workflow_id = "wf-1"
        execution.status = None

        await executor.execute(execution, nodes, edges, input_data, user_id="user-1")

        # 验证
        assert execution.status.value == "success" or execution.status == "success"

    async def test_condition_branch(self, executor, mock_db):
        """测试条件分支路由"""
        nodes = [
            {"id": "start", "type": "startNode", "data": {"inputs": [{"name": "score", "type": "number"}]}},
            {"id": "cond", "type": "conditionNode", "data": {
                "conditions": [{"id": "c1", "variable": "${start.score}", "operator": "gte", "value": 60}],
                "branches": [{"id": "pass", "condition_id": "c1"}, {"id": "fail", "condition_id": None}],
            }},
            {"id": "pass_node", "type": "endNode", "data": {"output_mapping": {"result": "通过"}}},
            {"id": "fail_node", "type": "endNode", "data": {"output_mapping": {"result": "失败"}}},
        ]
        edges = [
            {"source": "start", "target": "cond"},
            {"source": "cond", "target": "pass_node", "sourceHandle": "pass"},
            {"source": "cond", "target": "fail_node", "sourceHandle": "fail"},
        ]

        # 分数 >= 60 → 走 pass 分支
        execution = MagicMock()
        execution.id = "exec-2"
        execution.workflow_id = "wf-1"
        await executor.execute(execution, nodes, edges, {"score": 80}, user_id="user-1")

        # fail_node 应该被跳过

    async def test_cancellation(self, executor, mock_db):
        """测试执行取消"""
        executor.cancellation_mgr.is_cancelled = AsyncMock(return_value=True)

        execution = MagicMock()
        execution.id = "exec-3"
        nodes = [{"id": "start", "type": "startNode", "data": {}}]
        edges = []

        await executor.execute(execution, nodes, edges, {}, user_id="user-1")
        assert execution.status.value == "cancelled"
```

### 12.2 拓扑排序测试

```python
# tests/test_execution/test_topo_sorter.py

from app.services.execution.topo_sorter import TopoSorter


class TestTopoSorter:

    def test_linear_sort(self):
        """线性工作流排序"""
        nodes = [
            {"id": "A", "type": "startNode", "data": {}},
            {"id": "B", "type": "agentNode", "data": {}},
            {"id": "C", "type": "endNode", "data": {}},
        ]
        edges = [
            {"source": "A", "target": "B"},
            {"source": "B", "target": "C"},
        ]
        sorter = TopoSorter(nodes, edges)
        result = sorter.sort()
        assert [r["node"]["id"] for r in result] == ["A", "B", "C"]

    def test_parallel_sort(self):
        """并行工作流排序"""
        nodes = [
            {"id": "A", "type": "startNode", "data": {}},
            {"id": "B", "type": "agentNode", "data": {}},
            {"id": "C", "type": "agentNode", "data": {}},
            {"id": "D", "type": "endNode", "data": {}},
        ]
        edges = [
            {"source": "A", "target": "B"},
            {"source": "A", "target": "C"},
            {"source": "B", "target": "D"},
            {"source": "C", "target": "D"},
        ]
        sorter = TopoSorter(nodes, edges)
        result = sorter.sort()
        # A → [B, C] (同层) → D
        ids = [r["node"]["id"] for r in result]
        assert ids[0] == "A"
        assert set(ids[1:3]) == {"B", "C"}
        assert ids[3] == "D"

    def test_condition_skip(self):
        """条件分支跳过标记"""
        nodes = [
            {"id": "A", "type": "conditionNode", "data": {}},
            {"id": "B", "type": "agentNode", "data": {}},
            {"id": "C", "type": "agentNode", "data": {}},
        ]
        edges = [
            {"source": "A", "target": "B", "sourceHandle": "branch_true"},
            {"source": "A", "target": "C", "sourceHandle": "branch_false"},
        ]
        sorter = TopoSorter(nodes, edges)
        sorter.mark_branch_result("A", "branch_true", edges)
        assert sorter.should_skip("C")
        assert not sorter.should_skip("B")
```

### 12.3 变量解析测试

```python
# tests/test_execution/test_variable_resolver.py

from app.services.execution.variable_resolver import VariableResolver


class TestVariableResolver:

    def test_single_reference(self):
        """单一变量引用 → 返回原始类型"""
        resolver = VariableResolver()
        assert resolver.resolve("${node_1.result}", {"node_1.result": "hello"}) == "hello"
        assert resolver.resolve("${node_1.count}", {"node_1.count": 42}) == 42
        assert resolver.resolve("${node_1.data}", {"node_1.data": {"key": "val"}}) == {"key": "val"}

    def test_mixed_text(self):
        """混合文本 → 返回字符串"""
        resolver = VariableResolver()
        result = resolver.resolve("Hello ${node_1.name}!", {"node_1.name": "World"})
        assert result == "Hello World!"

    def test_dict_resolution(self):
        """字典中变量解析"""
        resolver = VariableResolver()
        result = resolver.resolve(
            {"key": "${node_1.value}"},
            {"node_1.value": 123}
        )
        assert result == {"key": 123}

    def test_list_resolution(self):
        """列表中变量解析"""
        resolver = VariableResolver()
        result = resolver.resolve(
            ["${a.x}", "${b.y}"],
            {"a.x": 1, "b.y": 2}
        )
        assert result == [1, 2]

    def test_unresolved_reference(self):
        """未解析的引用 → 保留原样"""
        resolver = VariableResolver()
        result = resolver.resolve("${node_x.missing}", {})
        assert result == "${node_x.missing}"

    def test_env_variable(self):
        """环境变量引用"""
        resolver = VariableResolver()
        result = resolver.resolve("${env.API_KEY}", {})
        assert result == "${env.API_KEY}"  # 保留原样，由 ExecutionContext 处理

    def test_extract_refs(self):
        """提取所有变量引用"""
        resolver = VariableResolver()
        refs = resolver.extract_refs({
            "a": "${node_1.x}",
            "b": "text ${node_2.y} more ${node_3.z}",
            "c": [1, "${env.SECRET}"],
        })
        assert set(refs) == {"node_1.x", "node_2.y", "node_3.z", "env.SECRET"}
```

### 12.4 节点执行器测试

```python
# tests/test_execution/test_node_executors.py

import pytest
from app.services.node_executors.condition_executor import ConditionExecutor
from app.services.node_executors.template_executor import TemplateExecutor
from app.services.node_executors.test_executor import TestExecutor
from app.services.node_executors.aggregate_executor import VariableAggregateExecutor
from app.services.node_executors.base import ExecutionContext


class TestConditionExecutor:

    @pytest.fixture
    def executor(self):
        return ConditionExecutor()

    @pytest.fixture
    def context(self):
        return ExecutionContext(
            execution_id="test", workflow_id="test", user_id="test",
            db_session=None, redis_client=None, broadcaster=None,
            cancellation_mgr=None, review_mgr=None,
        )

    async def test_equals_match(self, executor, context):
        config = {
            "conditions": [{"id": "c1", "variable": "${input.status}", "operator": "equals", "value": "active"}],
            "branches": [{"id": "b1", "condition_id": "c1"}, {"id": "b2", "condition_id": None}],
        }
        variables = {"input.status": "active"}
        result = await executor.execute(config, variables, context)
        assert result.output["matched_branch"] == "b1"

    async def test_contains_match(self, executor, context):
        config = {
            "conditions": [{"id": "c1", "variable": "${input.text}", "operator": "contains", "value": "error"}],
            "branches": [{"id": "b1", "condition_id": "c1"}, {"id": "b2", "condition_id": None}],
        }
        variables = {"input.text": "an error occurred"}
        result = await executor.execute(config, variables, context)
        assert result.output["matched_branch"] == "b1"

    async def test_default_branch(self, executor, context):
        config = {
            "conditions": [{"id": "c1", "variable": "${input.x}", "operator": "equals", "value": "yes"}],
            "branches": [{"id": "b1", "condition_id": "c1"}, {"id": "b_default", "condition_id": None}],
        }
        variables = {"input.x": "no"}
        result = await executor.execute(config, variables, context)
        assert result.output["matched_branch"] == "b_default"


class TestTemplateExecutor:

    @pytest.fixture
    def executor(self):
        return TemplateExecutor()

    @pytest.fixture
    def context(self):
        return ExecutionContext(
            execution_id="test", workflow_id="test", user_id="test",
            db_session=None, redis_client=None, broadcaster=None,
            cancellation_mgr=None, review_mgr=None,
        )

    async def test_basic_template(self, executor, context):
        config = {
            "template": "Hello {{ name }}, you have {{ count }} messages.",
            "input_mapping": {"name": "${user.name}", "count": "${user.count}"},
        }
        variables = {"user.name": "Alice", "user.count": 5}
        result = await executor.execute(config, variables, context)
        assert result.output["rendered_text"] == "Hello Alice, you have 5 messages."


class TestTestExecutor:

    @pytest.fixture
    def executor(self):
        return TestExecutor()

    @pytest.fixture
    def context(self):
        return ExecutionContext(
            execution_id="test", workflow_id="test", user_id="test",
            db_session=None, redis_client=None, broadcaster=None,
            cancellation_mgr=None, review_mgr=None,
        )

    async def test_all_pass(self, executor, context):
        config = {
            "assertions": [
                {"variable": "${agent.result}", "operator": "is_not_empty"},
                {"variable": "${agent.result}", "operator": "contains", "expected": "function"},
            ],
            "on_failure": "abort",
        }
        variables = {"agent.result": "function hello() {}"}
        result = await executor.execute(config, variables, context)
        assert result.output["all_passed"] is True
        assert result.error is None

    async def test_failure_abort(self, executor, context):
        config = {
            "assertions": [
                {"variable": "${agent.result}", "operator": "is_not_empty"},
            ],
            "on_failure": "abort",
        }
        variables = {"agent.result": ""}
        result = await executor.execute(config, variables, context)
        assert result.output["all_passed"] is False
        assert result.error is not None
```

### 12.5 WebSocket 测试

```python
# tests/test_execution/test_ws_broadcaster.py

import pytest
import json
from unittest.mock import AsyncMock
from app.services.execution.ws_broadcaster import ConnectionManager


class TestWSBroadcaster:

    @pytest.fixture
    def manager(self):
        return ConnectionManager()

    async def test_broadcast_message(self, manager):
        """测试广播消息"""
        ws = AsyncMock()
        await manager.connect("exec-1", ws)

        await manager.broadcast("exec-1", {"type": "test", "data": "hello"})

        ws.send_text.assert_called_once()
        sent_data = json.loads(ws.send_text.call_args[0][0])
        assert sent_data["type"] == "test"
        assert sent_data["data"] == "hello"

    async def test_disconnect_cleanup(self, manager):
        """测试断连清理"""
        ws = AsyncMock()
        await manager.connect("exec-1", ws)
        assert manager.get_connection_count("exec-1") == 1

        await manager.disconnect("exec-1", ws)
        assert manager.get_connection_count("exec-1") == 0

    async def test_dead_connection_cleanup(self, manager):
        """测试死连接自动清理"""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws2.send_text.side_effect = Exception("Connection closed")

        await manager.connect("exec-1", ws1)
        await manager.connect("exec-1", ws2)

        await manager.broadcast("exec-1", {"type": "test"})

        # ws1 成功，ws2 被移除
        assert manager.get_connection_count("exec-1") == 1
```

---

## 13. 给 Cursor 的额外说明

### 13.1 实现顺序建议

请按以下顺序实现，每个步骤完成后确保可运行：

```
Step 1: 基础框架
  ├── 创建 app/services/execution/ 目录
  ├── 实现 VariableResolver（独立可测试）
  ├── 实现 TopoSorter（独立可测试）
  └── 编写对应单元测试，确保通过

Step 2: 执行上下文
  ├── 实现 ExecutionContext
  ├── 实现 CancellationManager（Redis）
  └── 实现 WSBroadcaster（连接管理）

Step 3: 节点执行器
  ├── 实现 StartExecutor 和 EndExecutor（新增）
  ├── 扩展 Phase 4 的 12 种执行器为工作流版本
  ├── 实现 ReviewExecutor 和 TestExecutor（新增）
  └── 更新 NodeExecutorRegistry 注册所有 16 种

Step 4: 执行引擎核心
  ├── 实现 WorkflowExecutor（主类）
  ├── 实现并行执行逻辑（_execute_parallel）
  ├── 实现循环迭代逻辑（_execute_loop）
  ├── 实现审核暂停逻辑（_execute_review）
  └── 编写集成测试

Step 5: Service 层 + API
  ├── 实现 ExecutionService
  ├── 实现 LogService
  ├── 实现 API 路由（executions.py）
  ├── 实现 WebSocket 路由（ws.py）
  └── 实现 ReviewManager

Step 6: 集成测试
  ├── 端到端工作流执行测试
  ├── WebSocket 推送测试
  ├── 审核暂停/恢复测试
  └── 取消执行测试
```

### 13.2 关键设计决策

1. **后台执行模式**：工作流执行使用 `asyncio.create_task` 在后台运行，API 立即返回 execution_id。前端通过 WebSocket 监听进度。

2. **上下文隔离**：每个执行创建独立的 `ExecutionContext`，不同执行之间互不影响。

3. **变量解析策略**：
   - 单一引用 `${var}` 保留原始类型（dict/list/int 等）
   - 混合文本 `"Hello ${var}"` 转为字符串
   - 环境变量 `${env.XXX}` 由 ExecutionContext 特殊处理

4. **取消机制**：使用 Redis 存储取消标志，每个节点执行前检查。延时节点使用分段等待（每秒检查一次）。

5. **审核暂停**：使用 Redis Pub/Sub 实现信号传递。WorkflowExecutor 暂停在 `await review_mgr.wait_for_review()`，审核提交后通过 `redis.publish` 唤醒。

6. **并行执行**：使用 `asyncio.gather` 并发执行分支。分支间变量隔离，通过 VariableAggregate 节点合并。

7. **循环迭代**：同步遍历数组，每次迭代设置迭代变量，执行子节点序列。支持取消检查。

### 13.3 注意事项

1. **数据库 Session 生命周期**：后台任务中的 db session 需要独立于请求生命周期。建议在 `ExecutionService._run_execution` 中创建新的 session。

2. **WebSocket 认证**：WebSocket 不支持 Header 认证，通过 URL 查询参数 `?token=xxx` 传递 JWT。

3. **错误传播**：节点执行失败时，根据节点的 `on_failure` 配置决定是否终止整个工作流。默认 `abort`（终止）。

4. **Token 统计**：只有 Agent/Classify/Extract 节点会消耗 Token，其他节点 `tokens_used=None`。

5. **内存管理**：执行上下文中的 `_node_outputs` 会持续增长，对于大型工作流建议在执行完成后释放。

6. **并发安全**：同一个工作流可以同时运行多个执行实例，每个实例有独立的 ExecutionContext。

7. **Phase 4 向后兼容**：Phase 4 的单节点调试 API (`POST /api/workflows/:id/test-node`) 保持不变，Phase 5 的执行器扩展不影响调试模式。

### 13.4 新增依赖

```txt
# 追加到 requirements.txt
jinja2>=3.1.3        # 模板渲染（如果 Phase 4 未添加）
```

Phase 5 不需要新增其他外部依赖，所有核心功能基于已有的 FastAPI + SQLAlchemy + Redis + httpx 实现。

### 13.5 环境变量

```bash
# .env 追加
EXECUTION_MAX_CONCURRENT=10      # 最大并发执行数
EXECUTION_DEFAULT_TIMEOUT=300    # 默认执行超时（秒）
REVIEW_DEFAULT_TIMEOUT=3600      # 审核默认超时（秒）
```

---

> **文档结束**  
> Phase 5 后端开发文档完成。按章节顺序实现，完成后即可获得完整的工作流执行引擎。

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
