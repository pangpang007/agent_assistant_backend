# Phase 6 实现计划

## 目标

补齐平台运营能力：模板、版本标签与深度 Diff、执行历史与统计、日志中心、环境变量管理。

## 完成清单

### 1. 数据层
- [x] `Template` 增加 `user_id` / `nodes_data` / `edges_data` / `is_preset`；`workflow_id` 可空且非唯一
- [x] `EnvVariable` ORM 声明 `(user_id, key)` 唯一约束
- [x] Alembic `007_phase6_templates_logs_env.py`（含 `pg_trgm` + message GIN）
- [x] `app/seeds/preset_templates.py` + 启动种子幂等写入 4 个预置模板

### 2. Service
- [x] `TemplateService` — 列表/详情/保存为模板/使用/删除
- [x] `VersionService` — `tag_version` / `remove_tag` + 节点边深度 Diff
- [x] `ExecutionService` — 时间筛选、节点统计、`get_stats`
- [x] `LogService` — 用户范围全局日志 + ILIKE 搜索
- [x] `EnvService` — CRUD、Fernet、secret 脱敏、类型不可改

### 3. API
- [x] `/api/templates`、`/api/executions`、`/api/logs`、`/api/env-vars`
- [x] `POST /api/workflows/{id}/save-as-template`
- [x] `POST|DELETE /api/workflows/{id}/versions/{ver}/tag`
- [x] Phase 5 取消/审核/节点明细仍挂在 `/api/executions`

### 4. 测试
- [x] `tests/test_version_diff.py`
- [x] `tests/test_env_var_key.py`

## 与规格文档的差异

1. 路由统一为无 `/v1` 前缀（与 Phase 6 文档及前端 `/api/...` 一致）；原 `/api/v1/executions` 等不再提供。
2. 预置模板主要在 `seed.py` 幂等插入，不强制写进 migration INSERT。
3. 模板列表/详情需登录（文档可选公开预置 GET）。
4. Secret 脱敏为 `****` + 后 4 位。
5. 使用已有 `ForbiddenException`，未单独定义 `ForbiddenError`。
6. 执行取消额外提供 `POST /executions/{id}/stop`；审核额外提供 `POST /executions/{id}/review`（body 含 `node_id`/`nodeId`）以兼容前端。

## 本地验收

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
pytest tests/test_version_diff.py tests/test_env_var_key.py -v
```

## 关键约束

- 预置模板 `is_preset=true` 不可改删；`user_id` 为 NULL
- 使用模板时对 `nodes_data`/`edges_data` 深拷贝
- 所有环境变量均 Fernet 加密；API 仅对 `string` 返回明文
- 执行/日志权限经 `execution → workflow → user_id` 校验
