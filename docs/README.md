# 项目文档

按开发阶段组织文档，每个 Phase 独立一个文件夹，包含**开发文档**与**实施计划**两类文件。

## 目录结构

```
docs/
├── README.md                 # 本文件：文档总索引
├── phase0/                   # Phase 0：后端脚手架
│   ├── README.md
│   ├── development.md        # 开发规格文档
│   └── implementation-plan.md # 实施计划
├── phase1/                   # Phase 1：（待补充）
│   └── README.md
└── ...
```

## 各阶段文档

| 阶段 | 说明 | 状态 |
|------|------|------|
| [Phase 0](phase0/README.md) | 后端脚手架：ORM、中间件、健康检查、Docker | 已完成 |
| [Phase 1](phase1/README.md) | 用户系统：注册、登录、团队管理 | 已完成 |
| [Phase 2](phase2/README.md) | Agent / Tool / Model 管理 | 已完成 |
| [Phase 3](phase3/README.md) | 知识库管理（RAG） | 已完成 |
| [Phase 4](phase4/README.md) | 工作流编辑器后端 | 已完成 |
| [Phase 5](phase5/README.md) | 工作流执行引擎 | 已完成 |
| [Phase 6](phase6/README.md) | 模板 / 版本标签 / 执行历史 / 日志 / 环境变量 | 已完成 |

## 文档规范

每个 Phase 文件夹应包含：

1. **README.md** — 阶段概述与文档索引
2. **development.md** — 面向 AI Agent / 开发者的完整规格说明
3. **implementation-plan.md** — 分步骤实施计划与验收标准

新增阶段时，复制 `phase1/README.md` 模板并补充对应文档即可。
