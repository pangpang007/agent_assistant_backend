# Phase 5：工作流执行引擎

## 文档

| 文件 | 说明 |
|------|------|
| [development.md](development.md) | 完整开发规格 |
| [implementation-plan.md](implementation-plan.md) | 实施计划与验收清单 |

## 范围

- 拓扑排序执行引擎（条件跳过、并行、循环、审核暂停）
- 变量解析（`${node.field}` / `${env.XXX}`）
- 执行记录 / 节点详情 / 日志查询
- 取消执行、审核通过/拒绝恢复
- WebSocket 实时状态推送
- Start / End / Review / Test 节点执行器

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/workflows/{id}/run` | 启动执行（后台任务，立即返回 `execution_id`） |
| GET | `/api/v1/executions` | 执行列表 |
| GET | `/api/v1/executions/{id}` | 执行详情 |
| GET | `/api/v1/executions/{id}/nodes` | 节点执行明细 |
| GET | `/api/v1/executions/{id}/logs` | 执行日志 |
| POST | `/api/v1/executions/{id}/cancel` | 取消执行 |
| POST | `/api/v1/executions/{id}/review` | 审核操作（resume） |
| WS | `/api/ws/executions/{id}?token=` | 实时推送 |

## 状态

**已完成**（单元测试：`test_execution_topo` / `test_variable_resolver`；端到端需 PostgreSQL + Redis）
