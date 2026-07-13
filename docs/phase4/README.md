# Phase 4：工作流编辑器后端

## 文档

| 文件 | 说明 |
|------|------|
| [development.md](development.md) | 完整开发规格 |
| [implementation-plan.md](implementation-plan.md) | 实施计划与验收清单 |

## 范围

- 工作流 CRUD + 自动版本管理
- 校验引擎（连通性、环检测、变量引用）
- 单节点调试（Agent / 知识检索 / 代码 / HTTP / 模板 / 条件等）
- 导入/导出 JSON
- WebSocket Schema 定义（Phase 5 实现）

## API 前缀

`/api/workflows`

## 状态

**已完成**（集成测试需 PostgreSQL + Redis）
