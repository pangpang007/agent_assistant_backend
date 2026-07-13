# Phase 2 实现计划

## 目标

实现 Agent CRUD、Tool 系统、Model 管理三大模块，含预置数据 seed、API Key 加密/脱敏、工具测试调用。

## 完成清单

### 1. 基础设施
- [x] `app/core/config.py` — tool 安全配置
- [x] `app/core/encryption.py` — Fernet 加密/脱敏
- [x] `app/core/tool_security.py` — URL 安全校验
- [x] `app/core/seed.py` — 6 预置 Agent + 7 预置 Tool
- [x] `app/main.py` lifespan 调用 seed

### 2. 数据层
- [x] 重构 `Agent` / `Tool` / `ModelProvider` 模型
- [x] 新增 `LLMModel`、`AgentTool`、`AgentKnowledgeBase`
- [x] 扩展 `enums.py`（ProviderType、AuthType）
- [x] Alembic `003_phase2_agent_tool_model.py`

### 3. API 层（23 个端点）
- [x] `/api/agents/*` — 列表、详情、CRUD、复制
- [x] `/api/tools/*` — 列表、详情、CRUD、测试调用
- [x] `/api/models/*` — 供应商、模型、用量统计

### 4. 测试
- [x] `tests/test_agents.py`
- [x] `tests/test_tools.py`
- [x] `tests/test_models.py`（模型 API；原 schema 测试重命名为 `test_db_schema.py`）

## 本地验收

```bash
# 1. 迁移
alembic upgrade head

# 2. 启动
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. 测试（需 PostgreSQL tangyuan_test 库）
pytest tests/test_agents.py tests/test_tools.py tests/test_models.py -v
```

## 关键约束

- 预置资源 `user_id=NULL`，不可编辑/删除
- 仅预置 Agent 可复制
- API Key / auth_config 使用 Fernet 加密，响应脱敏
- Agent `model_id` 指向 `llm_models.id`
