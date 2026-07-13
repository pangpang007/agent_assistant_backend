# Phase 3：知识库管理（RAG）

## 文档

| 文件 | 说明 |
|------|------|
| [development.md](development.md) | 完整开发规格 |
| [implementation-plan.md](implementation-plan.md) | 实施计划与验收清单 |

## 范围

- 知识库 CRUD + 分块配置
- 文档上传 / 删除 / 重新处理 / 状态查询
- 文档处理 Pipeline：提取 → 分块 → Embedding → pgvector
- 向量检索 API
- Celery 异步任务
- Agent 关联知识库（`agent_knowledge_bases`）

## API 前缀

`/api/knowledge`

## 状态

**已完成**（需 PostgreSQL + Redis + Celery Worker 做完整验收）
