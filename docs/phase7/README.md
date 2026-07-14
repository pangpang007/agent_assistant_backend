# Phase 7：Dashboard + API 发布 + 全局打磨

## 文档

| 文件 | 说明 |
|------|------|
| [development.md](development.md) | 完整开发规格 |
| [implementation-plan.md](implementation-plan.md) | 实施计划与验收清单 |

## 范围

- Dashboard：统计概览、Token 趋势、最近工作流/执行（Redis 缓存）
- 工作流发布为 API：生成 `sk-` Key、启停、重置、取消发布
- 外部调用：`POST /api/published/{api_key}/run`（API Key 认证 + 限流）
- 全局搜索：工作流 / Agent / 知识库 / 模板
- 安全加固：安全响应头、请求体限制、全局限流

## API 前缀

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard/stats` | 概览统计 |
| GET | `/api/dashboard/token-usage` | Token 趋势 |
| GET | `/api/dashboard/recent-workflows` | 最近工作流 |
| GET | `/api/dashboard/recent-executions` | 最近执行 |
| POST/DELETE | `/api/workflows/{id}/publish-api` | 发布 / 取消 |
| POST | `/api/workflows/{id}/publish-api/reset-key` | 重置 Key |
| GET | `/api/published-apis` | 已发布列表 |
| PUT | `/api/published-apis/{id}/toggle` | 启用/停用 |
| POST | `/api/published/{api_key}/run` | 外部调用 |
| GET | `/api/search` | 全局搜索 |

## 状态

**已完成**（单元测试：`test_api_key` / `test_search_scoring` / `test_rate_limit_logic`；端到端需 PostgreSQL + Redis）
