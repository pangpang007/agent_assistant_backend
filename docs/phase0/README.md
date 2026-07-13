# Phase 0 — 后端脚手架

搭建「汤圆的代码助手」FastAPI 后端项目脚手架：15 张表 ORM/Schema、基础中间件、健康检查、Docker Compose 本地环境。

**项目代号**：`tangyuan-backend`  
**状态**：已完成

## 文档

| 文件 | 说明 |
|------|------|
| [development.md](development.md) | 完整开发规格（技术栈、模型定义、中间件、配置、验证清单等） |
| [implementation-plan.md](implementation-plan.md) | 分 6 步的实施计划、架构图与验收标准 |

## 完成标准

- `uvicorn app.main:app --reload` 正常启动
- `GET /api/health` 返回 healthy（需 PostgreSQL + Redis 就绪）
- `alembic upgrade head` 创建 15 张表
- `pytest tests/` 全部通过
