# Phase 5 实现计划

## 目标

实现工作流执行引擎：按拓扑序跑节点、支持条件/并行/循环/审核暂停，并通过 REST + WebSocket 对外暴露执行生命周期。

## 完成清单

### 1. 数据层
- [x] Alembic `006_phase5_execution_indexes.py`（executions / logs 查询索引）
- [x] 复用 Phase 0–4 已有 `Execution` / `ExecutionNode` / `Log` 模型与枚举

### 2. 执行引擎核心（`app/services/execution/`）
- [x] `TopoSorter` — 拓扑排序 + 条件分支 skip
- [x] `VariableResolver` — 单一引用保留类型、混合文本转字符串
- [x] `ExecutionContext` — 全局输入、节点输出、图结构
- [x] `CancellationManager` — Redis 取消标志
- [x] `ReviewManager` — 审核等待 / Pub-Sub 唤醒
- [x] `WSBroadcaster` — 按 execution_id 广播
- [x] `WorkflowExecutor` — 主循环、并行、循环、审核 checkpoint 暂停/恢复

### 3. 节点执行器
- [x] `StartExecutor` / `EndExecutor` / `ReviewExecutor` / `TestExecutor`
- [x] Registry 注册全部节点类型（含 Phase 4 已有 12 种）
- [x] 包名保持 `workflow_executors/`（与 Phase 4 一致，未改名 `node_executors/`）

### 4. Service + API
- [x] `ExecutionService` — 启动后台任务、列表/详情、取消、审核恢复
- [x] `LogService` — 日志分页查询
- [x] `POST /api/workflows/{id}/run`
- [x] `/api/v1/executions` REST
- [x] `WS /api/ws/executions/{id}`（token 查询参数验权）

### 5. 测试
- [x] `tests/test_execution_topo.py`
- [x] `tests/test_variable_resolver.py`

### 6. 配置
- [x] `EXECUTION_MAX_CONCURRENT` / `EXECUTION_DEFAULT_TIMEOUT` / `REVIEW_DEFAULT_TIMEOUT`

## 与规格文档的差异

1. **WebSocket 路径**：实现为 `/api/ws/executions/{id}`，便于挂到独立 `ws` 路由，而非文档示例的 `/api/executions/{id}/stream`。
2. **审核恢复**：首次执行到 review 节点时写入 Redis checkpoint 并暂停；审核 API 校验后另起后台任务从 checkpoint 恢复（不长期占用同一 coroutine 的 `wait_for_review`）。
3. **执行器包名**：沿用 `app/services/workflow_executors/`。
4. **Agent/知识节点**：复用 Phase 4 执行器，未单独扩展 ModelUsage / 重试策略（可在后续 Phase 增强）。

## 本地验收

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
pytest tests/test_execution_topo.py tests/test_variable_resolver.py -v
```

## 关键约束

- 执行使用独立 DB session 的后台 `asyncio.create_task`，API 立即返回
- 取消通过 Redis 标志，在节点边界检查
- WebSocket 使用 `?token=` 传递 JWT access token
- Phase 4 `POST .../nodes/test` 单节点调试保持不变
