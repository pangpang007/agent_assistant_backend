# Phase 6：模板 + 版本标签 + 执行历史 + 日志中心 + 环境变量

## 文档

| 文件 | 说明 |
|------|------|
| [development.md](development.md) | 完整开发规格 |
| [implementation-plan.md](implementation-plan.md) | 实施计划与验收清单 |

## 范围

- 模板系统：预置模板种子、CRUD、从工作流保存、使用模板创建工作流
- 版本管理增强：手动打标签/删标签、深度 Diff
- 执行历史：列表筛选、详情统计、`/stats` 聚合
- 日志中心：全局列表、筛选、消息模糊搜索
- 环境变量：Fernet 加密、secret 脱敏、key 格式与唯一约束

## API 前缀

| 前缀 | 说明 |
|------|------|
| `/api/templates` | 模板 |
| `/api/workflows/.../save-as-template` | 工作流存为模板 |
| `/api/workflows/.../versions/:ver/tag` | 版本标签 |
| `/api/executions` | 执行历史（含 `/stats`） |
| `/api/logs` | 日志中心 |
| `/api/env-vars` | 环境变量 |

## 状态

**已完成**（单元测试：`test_version_diff` / `test_env_var_key`；端到端需 PostgreSQL + Redis）
