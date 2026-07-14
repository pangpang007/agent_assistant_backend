# Phase 7 实现计划

## 目标

完成项目收官能力：Dashboard、工作流 API 发布与外部调用、全局搜索、缓存与安全加固。

## 完成清单

### 1. 数据层
- [x] Alembic `008_phase7_dashboard_api.py`
- [x] `Execution.source` / `api_caller_workflow_id`
- [x] `Workflow` API 统计字段 + `api_is_active`
- [x] `published_api_key`：UUID → `String(64)`（`sk-` + 32 hex）
- [x] pg_trgm 搜索索引与发布列表部分索引（幂等）

### 2. 核心能力
- [x] `app/core/api_key_auth.py` — 生成 / 脱敏 / 哈希 / 解析工作流
- [x] Phase 7 异常类与配置项（限流、缓存 TTL、外部超时）

### 3. Service
- [x] `DashboardService` — 统计 JOIN `workflows`（无 `executions.user_id`）+ Redis 缓存
- [x] `PublishApiService` — 发布幂等、取消、重置、列表、启停
- [x] `SearchService` — ILIKE 多资源搜索
- [x] `ExternalExecutionService` — 同步等待 `WorkflowExecutor` + API 统计原子更新
- [x] `RateLimitService` / `CacheInvalidator`

### 4. API + 中间件
- [x] `/api/dashboard/*`、`/api/published-apis`、`/api/search`、`/api/published/{key}/run`
- [x] workflows `publish-api` / `reset-key`
- [x] 安全响应头、请求体大小限制、全局限流中间件
- [x] Web 触发执行写入 `source=web`

### 5. 测试
- [x] `tests/test_api_key.py`
- [x] `tests/test_search_scoring.py`
- [x] `tests/test_rate_limit_logic.py`

## 与规格文档的差异

1. **无 `executions.user_id`**：Dashboard / 最近执行经 `workflows.user_id` JOIN；索引使用 `workflow_id + started_at`。
2. **外部认证**：路径参数 `api_key` 为主；若带 `X-API-Key` 则必须一致。
3. **执行器签名**：复用 Phase 5 `WorkflowExecutor.execute(execution, nodes_data, edges_data, input_data, user_id)`。
4. **Agent 计数**：当前用户自有 Agent **或** 预置 Agent（`is_preset`）。
5. 全局限流对 `/api/health`、`/api/crypto`、OpenAPI 文档放宽/跳过。

## 本地验收

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
pytest tests/test_api_key.py tests/test_search_scoring.py tests/test_rate_limit_logic.py -v
```

## 关键约束

- 发布幂等：已发布再次 publish 返回原 Key
- 外部调用必须写入 `Execution.source=api` 并更新 `api_*` 统计
- 列表接口只返回脱敏 API Key；完整 Key 仅在发布/重置时返回
- Dashboard 缓存最终一致（默认 TTL 60s）
