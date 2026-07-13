# Phase 2：Agent + Tool + Model 管理

## 文档

| 文件 | 说明 |
|------|------|
| [development.md](development.md) | 完整开发规格（API、模型、Service、测试） |
| [implementation-plan.md](implementation-plan.md) | 实施计划与验收清单 |

## 范围

- Agent CRUD + 预置 Agent 复制
- Tool CRUD + OpenAPI 配置 + 测试调用
- Model Provider / LLM Model 管理 + 用量统计
- 预置数据：6 个 Agent、7 个 Tool

## API 前缀

- `/api/agents`
- `/api/tools`
- `/api/models`

## 状态

**已完成**（代码已实现，需 PostgreSQL 运行迁移与测试）
