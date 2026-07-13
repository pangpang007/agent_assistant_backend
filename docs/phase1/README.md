# Phase 1 — 用户系统

> **状态**：已完成

## 文档

| 文件 | 说明 |
|------|------|
| [development.md](development.md) | 完整开发规格 |
| [implementation-plan.md](implementation-plan.md) | 分 9 步实施计划、验收清单与 API 总表 |

## 范围

- 用户注册 / 登录 / JWT 认证 / 登出（Token 黑名单）
- 个人资料管理、修改密码
- 团队创建、邀请码加入、成员管理

## API 前缀

- `/api/auth/*` — 认证
- `/api/users/*` — 用户资料
- `/api/teams/*` — 团队管理
