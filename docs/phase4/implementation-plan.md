# Phase 4 实现计划

## 目标

实现工作流编辑器完整后端：CRUD、版本管理、校验引擎、单节点调试、导入/导出。

## 完成清单

### 1. 数据层
- [x] `Workflow` / `WorkflowVersion` 字段重命名 `nodes_data` / `edges_data`
- [x] Alembic `005_phase4_workflow_rename.py`
- [x] `NodeType` 枚举

### 2. 服务层
- [x] `WorkflowService` — CRUD + 导入/导出
- [x] `VersionService` — 版本列表/详情/回滚/Diff
- [x] `ValidationService` — 校验引擎
- [x] `NodeTestService` + 节点执行器

### 3. API
- [x] `/api/workflows` — CRUD、版本、校验、单节点调试、导入/导出
- [x] `app/schemas/websocket.py` — Phase 5 消息格式定义

### 4. 测试
- [x] `test_workflow_validation.py` / `test_node_test.py`（单元测试）
- [x] `test_workflows.py` / `test_workflow_versions.py` / `test_workflow_import_export.py`

## 本地验收

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
pytest tests/test_workflow_validation.py tests/test_node_test.py -v
```

## 关键约束

- 仅 `nodes_data`/`edges_data` 变更时自动创建新版本
- 校验接口始终返回 200，`is_valid` 在 data 中
- 代码执行在子进程沙箱中运行
