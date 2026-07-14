---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 4263223131904378_0/project_7661866342080954651-files/Phase6/phase6_backend.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 4263223131904378#1784021207174
    ReservedCode2: ""
---
# 汤圆的代码助手 - Phase 6 后端开发文档：模板 + 版本管理增强 + 执行历史 + 日志中心 + 环境变量管理

> **目标读者**：Cursor / AI Coding Agent  
> **版本**：Phase 6 v1.0  
> **项目代号**：`tangyuan-backend`  
> **前置条件**：Phase 0（脚手架 + 全部数据库模型）+ Phase 1（用户系统）+ Phase 2（Agent + 工具 + 模型管理）+ Phase 3（知识库管理）+ Phase 4（工作流编辑器后端）+ Phase 5（执行引擎）已完成

---

## 1. 目标

在 Phase 0-5 基础上，实现平台级别的运营与治理能力：

### A. 模板系统
- Template 模型完善（新增 `user_id`、`nodes_data`、`edges_data`、`is_preset` 字段）
- 4 个预置模板种子数据
- 模板 CRUD + 搜索 + 分类筛选
- 从工作流保存为模板
- 使用模板创建新工作流（复制节点/边数据）
- 预置模板不可删除/修改

### B. 版本管理增强
- 在 Phase 4 已有版本管理（列表/详情/回滚/diff）基础上增加：
  - 手动打标签 / 删标签
  - 版本对比算法增强（节点增删改精确检测）
  - 版本预览（只读获取指定版本完整数据，复用 Phase 4 接口）

### C. 执行历史
- 复用 Phase 5 产生的 Execution / ExecutionNode 记录
- 列表查询（分页 + 按工作流/状态/时间筛选）
- 执行详情（含所有 ExecutionNode + 统计汇总）
- 执行统计聚合（按天/按工作流的成功率、平均耗时）

### D. 日志中心
- 全局日志列表（分页 + 按级别/执行ID/时间筛选）
- 日志详情
- 全文搜索 message 字段

### E. 环境变量管理
- EnvVariable 模型增强（新增 `(user_id, key)` 复合唯一约束）
- CRUD 完整实现
- Secret 类型 Fernet 加密存储，接口永远脱敏返回
- 变量名格式校验（大写字母 + 数字 + 下划线）
- 变量名唯一性校验

Phase 6 完成后，用户应能：浏览/使用/管理模板 → 查看执行历史和日志 → 管理环境变量 → 给版本打标签。

---

## 2. 数据库变更

### 2.1 Template 模型增强 `app/models/template.py`

Phase 0 的 Template 模型缺少 `user_id`、`nodes_data`/`edges_data`（用于模板独立存储画布数据，不依赖源工作流）、`is_preset` 字段。Phase 6 完善如下：

```python
# app/models/template.py — Phase 6 完整模型

import uuid
from typing import Optional
from datetime import datetime

from sqlalchemy import String, Integer, Boolean, Text, ForeignKey, DateTime, func, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin


class Template(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "templates"

    # Phase 6 新增：模板创建者
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Phase 0 原有字段保留
    workflow_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    use_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Phase 6 新增：独立存储画布数据（模板快照，不随源工作流变化）
    nodes_data: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    edges_data: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)

    # Phase 6 新增：是否为系统预置模板
    is_preset: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # Relationships
    user = relationship("User", backref="templates")
```

#### 字段变更汇总

| 变更项 | Phase 0 | Phase 6 |
|--------|---------|---------|
| `user_id` | 无 | **新增**，FK → users.id，ON DELETE SET NULL |
| `workflow_id` | NOT NULL, UNIQUE | 改为 **nullable**，去掉 UNIQUE（一个工作流可多次保存为模板） |
| `nodes_data` | 无 | **新增** JSONB，模板画布快照 |
| `edges_data` | 无 | **新增** JSONB，模板画布快照 |
| `is_preset` | 无 | **新增** BOOLEAN，标记预置模板 |

#### 新增索引

| 字段/组合 | 索引类型 | 说明 |
|-----------|---------|------|
| `(category, is_preset)` | 复合 INDEX | 按分类 + 预置标志筛选模板列表 |
| `(is_preset)` | INDEX | 快速区分预置/自定义模板 |

```python
# Alembic 迁移中新增索引
op.create_index("ix_templates_category_preset", "templates", ["category", "is_preset"])
op.create_index("ix_templates_is_preset", "templates", ["is_preset"])
```

---

### 2.2 EnvVariable 模型增强 `app/models/env_variable.py`

Phase 0 的 EnvVariable 缺少 `(user_id, key)` 复合唯一约束。Phase 6 补全：

```python
# app/models/env_variable.py — Phase 6 确认模型

import uuid
from typing import Optional
from datetime import datetime

from sqlalchemy import String, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin
from .enums import EnvVarType


class EnvVariable(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "env_variables"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    value_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[EnvVarType] = mapped_column(
        nullable=False, default=EnvVarType.string, server_default="string"
    )

    # Relationships
    user = relationship("User", back_populates="env_variables")

    # Phase 6 新增：复合唯一约束
    __table_args__ = (
        Index("uq_env_variables_user_key", "user_id", "key", unique=True),
    )
```

#### Alembic 迁移

```python
# 在迁移文件中添加
op.create_unique_constraint("uq_env_variables_user_key", "env_variables", ["user_id", "key"])
```

---

### 2.3 Log 表新增全文搜索索引

为支持日志全文搜索，在 `logs` 表的 `message` 字段上创建 GIN 索引：

```python
# Alembic 迁移中
from sqlalchemy import text

# 使用 pg_trgm 扩展支持模糊搜索
op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
op.execute(
    "CREATE INDEX ix_logs_message_trgm ON logs USING gin (message gin_trgm_ops)"
)
```

---

### 2.4 Execution 表新增索引

为支持执行统计聚合查询，新增索引：

```python
# Alembic 迁移中
op.create_index("ix_executions_workflow_status", "executions", ["workflow_id", "status"])
op.create_index("ix_executions_started_at", "executions", ["started_at"])
```

---

### 2.5 完整数据库变更汇总

| 表 | 变更类型 | 内容 |
|----|---------|------|
| `templates` | 新增字段 | `user_id`, `nodes_data`, `edges_data`, `is_preset` |
| `templates` | 修改字段 | `workflow_id` 改为 nullable，去掉 UNIQUE |
| `templates` | 新增索引 | `ix_templates_category_preset`, `ix_templates_is_preset` |
| `env_variables` | 新增约束 | `uq_env_variables_user_key` (user_id, key) UNIQUE |
| `logs` | 新增索引 | `ix_logs_message_trgm` GIN 索引 |
| `executions` | 新增索引 | `ix_executions_workflow_status`, `ix_executions_started_at` |

---

## 3. 预置模板数据（4 个）

在 Alembic 迁移或应用启动种子脚本中插入以下 4 个预置模板。预置模板的 `user_id = NULL`，`is_preset = True`，`workflow_id = NULL`。

### 3.1 模板 1：需求→开发→测试→上线 全流程

```python
preset_template_1 = {
    "id": "00000000-0000-0000-0000-000000000001",
    "user_id": None,
    "workflow_id": None,
    "name": "需求→开发→测试→上线 全流程",
    "description": "从产品需求分析到代码开发、测试验证的完整软件交付流水线。包含产品经理 Agent 分析需求、后端工程师 Agent 编写代码、测试工程师 Agent 生成测试用例并执行、Code Reviewer Agent 审查代码质量。",
    "category": "软件开发",
    "thumbnail_url": "/static/templates/full-cycle-dev.png",
    "use_count": 0,
    "is_preset": True,
    "nodes_data": [
        {
            "id": "node_start_1",
            "type": "startNode",
            "position": {"x": 100, "y": 300},
            "data": {
                "label": "需求输入",
                "inputs": [
                    {"name": "requirement", "type": "string", "description": "产品需求描述", "required": True, "default_value": None},
                    {"name": "priority", "type": "string", "description": "优先级(P0/P1/P2)", "required": False, "default_value": "P1"}
                ],
                "outputs": [
                    {"name": "requirement", "type": "string", "description": "需求描述"},
                    {"name": "priority", "type": "string", "description": "优先级"}
                ]
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_agent_pm",
            "type": "agentNode",
            "position": {"x": 400, "y": 200},
            "data": {
                "label": "产品经理 - 需求分析",
                "agent_id": "preset-pm",
                "input_mapping": {"user_query": "${node_start_1.requirement}", "priority": "${node_start_1.priority}"},
                "output_key": "prd_output"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_agent_backend",
            "type": "agentNode",
            "position": {"x": 700, "y": 200},
            "data": {
                "label": "后端工程师 - 代码开发",
                "agent_id": "preset-backend",
                "input_mapping": {"user_query": "${node_agent_pm.prd_output}"},
                "output_key": "code_output"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_agent_reviewer",
            "type": "agentNode",
            "position": {"x": 700, "y": 400},
            "data": {
                "label": "Code Reviewer - 代码审查",
                "agent_id": "preset-reviewer",
                "input_mapping": {"user_query": "${node_agent_backend.code_output}"},
                "output_key": "review_output"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_agent_tester",
            "type": "agentNode",
            "position": {"x": 1000, "y": 300},
            "data": {
                "label": "测试工程师 - 测试验证",
                "agent_id": "preset-tester",
                "input_mapping": {"user_query": "${node_agent_backend.code_output}", "review": "${node_agent_reviewer.review_output}"},
                "output_key": "test_output"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_end_1",
            "type": "endNode",
            "position": {"x": 1300, "y": 300},
            "data": {
                "label": "交付结果",
                "output_mapping": {
                    "prd": "${node_agent_pm.prd_output}",
                    "code": "${node_agent_backend.code_output}",
                    "review": "${node_agent_reviewer.review_output}",
                    "test_result": "${node_agent_tester.test_output}"
                }
            },
            "selected": False, "dragging": False
        }
    ],
    "edges_data": [
        {"id": "e1", "source": "node_start_1", "target": "node_agent_pm", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e2", "source": "node_agent_pm", "target": "node_agent_backend", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e3", "source": "node_agent_backend", "target": "node_agent_reviewer", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e4", "source": "node_agent_backend", "target": "node_agent_tester", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e5", "source": "node_agent_reviewer", "target": "node_agent_tester", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e6", "source": "node_agent_tester", "target": "node_end_1", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}}
    ]
}
```

### 3.2 模板 2：代码审查流水线

```python
preset_template_2 = {
    "id": "00000000-0000-0000-0000-000000000002",
    "user_id": None,
    "workflow_id": None,
    "name": "代码审查流水线",
    "description": "对提交的代码进行多维度审查：静态分析检查代码规范、安全扫描检查潜在漏洞、架构师评估设计方案合理性。最终汇总审查报告。",
    "category": "代码质量",
    "thumbnail_url": "/static/templates/code-review.png",
    "use_count": 0,
    "is_preset": True,
    "nodes_data": [
        {
            "id": "node_start_1",
            "type": "startNode",
            "position": {"x": 100, "y": 300},
            "data": {
                "label": "代码输入",
                "inputs": [
                    {"name": "code", "type": "string", "description": "待审查的代码", "required": True, "default_value": None},
                    {"name": "language", "type": "string", "description": "编程语言", "required": False, "default_value": "python"}
                ],
                "outputs": [
                    {"name": "code", "type": "string", "description": "代码内容"},
                    {"name": "language", "type": "string", "description": "编程语言"}
                ]
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_parallel_1",
            "type": "parallelNode",
            "position": {"x": 400, "y": 250},
            "data": {
                "label": "并行审查",
                "branches": [
                    {"id": "branch_style", "label": "代码规范审查"},
                    {"id": "branch_security", "label": "安全扫描"},
                    {"id": "branch_arch", "label": "架构评估"}
                ],
                "wait_mode": "all"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_agent_style",
            "type": "agentNode",
            "position": {"x": 700, "y": 100},
            "data": {
                "label": "Code Reviewer - 规范检查",
                "agent_id": "preset-reviewer",
                "input_mapping": {"user_query": "${node_start_1.code}", "language": "${node_start_1.language}"},
                "output_key": "style_review"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_agent_security",
            "type": "agentNode",
            "position": {"x": 700, "y": 300},
            "data": {
                "label": "后端工程师 - 安全扫描",
                "agent_id": "preset-backend",
                "input_mapping": {"user_query": "安全审查以下代码:\n${node_start_1.code}"},
                "output_key": "security_review"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_agent_arch",
            "type": "agentNode",
            "position": {"x": 700, "y": 500},
            "data": {
                "label": "架构师 - 设计评估",
                "agent_id": "preset-architect",
                "input_mapping": {"user_query": "${node_start_1.code}"},
                "output_key": "arch_review"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_aggregate_1",
            "type": "variableAggregateNode",
            "position": {"x": 1000, "y": 300},
            "data": {
                "label": "汇总审查结果",
                "aggregations": [
                    {"name": "all_reviews", "sources": ["${node_agent_style.style_review}", "${node_agent_security.security_review}", "${node_agent_arch.arch_review}"], "mode": "array"}
                ],
                "output_key": "aggregated_reviews"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_template_1",
            "type": "templateNode",
            "position": {"x": 1300, "y": 300},
            "data": {
                "label": "生成审查报告",
                "template": "# 代码审查报告\n\n## 代码规范\n{{ reviews[0] }}\n\n## 安全扫描\n{{ reviews[1] }}\n\n## 架构评估\n{{ reviews[2] }}\n\n---\n*本报告由自动审查流水线生成*",
                "input_mapping": {"reviews": "${node_aggregate_1.all_reviews}"},
                "output_key": "final_report"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_end_1",
            "type": "endNode",
            "position": {"x": 1600, "y": 300},
            "data": {
                "label": "输出报告",
                "output_mapping": {"report": "${node_template_1.final_report}"}
            },
            "selected": False, "dragging": False
        }
    ],
    "edges_data": [
        {"id": "e1", "source": "node_start_1", "target": "node_parallel_1", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e2", "source": "node_parallel_1", "target": "node_agent_style", "sourceHandle": "branch_style", "targetHandle": "input_1", "type": "default", "animated": False, "label": "规范", "data": {"condition_branch_id": "branch_style"}},
        {"id": "e3", "source": "node_parallel_1", "target": "node_agent_security", "sourceHandle": "branch_security", "targetHandle": "input_1", "type": "default", "animated": False, "label": "安全", "data": {"condition_branch_id": "branch_security"}},
        {"id": "e4", "source": "node_parallel_1", "target": "node_agent_arch", "sourceHandle": "branch_arch", "targetHandle": "input_1", "type": "default", "animated": False, "label": "架构", "data": {"condition_branch_id": "branch_arch"}},
        {"id": "e5", "source": "node_agent_style", "target": "node_aggregate_1", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e6", "source": "node_agent_security", "target": "node_aggregate_1", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e7", "source": "node_agent_arch", "target": "node_aggregate_1", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e8", "source": "node_aggregate_1", "target": "node_template_1", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e9", "source": "node_template_1", "target": "node_end_1", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}}
    ]
}
```

### 3.3 模板 3：文档生成工作流

```python
preset_template_3 = {
    "id": "00000000-0000-0000-0000-000000000003",
    "user_id": None,
    "workflow_id": None,
    "name": "文档生成工作流",
    "description": "根据主题自动生成完整的技术文档。包含大纲生成、分章节撰写、文档审核三个步骤，最终输出格式化的 Markdown 文档。",
    "category": "内容创作",
    "thumbnail_url": "/static/templates/doc-gen.png",
    "use_count": 0,
    "is_preset": True,
    "nodes_data": [
        {
            "id": "node_start_1",
            "type": "startNode",
            "position": {"x": 100, "y": 300},
            "data": {
                "label": "文档主题",
                "inputs": [
                    {"name": "topic", "type": "string", "description": "文档主题", "required": True, "default_value": None},
                    {"name": "target_audience", "type": "string", "description": "目标读者", "required": False, "default_value": "开发者"},
                    {"name": "style", "type": "string", "description": "文档风格", "required": False, "default_value": "技术文档"}
                ],
                "outputs": [
                    {"name": "topic", "type": "string"},
                    {"name": "target_audience", "type": "string"},
                    {"name": "style", "type": "string"}
                ]
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_agent_outline",
            "type": "agentNode",
            "position": {"x": 400, "y": 300},
            "data": {
                "label": "产品经理 - 生成大纲",
                "agent_id": "preset-pm",
                "input_mapping": {"user_query": "为以下主题生成详细的文档大纲，目标读者: ${node_start_1.target_audience}，风格: ${node_start_1.style}\n\n主题: ${node_start_1.topic}"},
                "output_key": "outline"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_agent_writer",
            "type": "agentNode",
            "position": {"x": 700, "y": 300},
            "data": {
                "label": "前端工程师 - 撰写文档",
                "agent_id": "preset-frontend",
                "input_mapping": {"user_query": "根据以下大纲撰写完整的文档内容，风格: ${node_start_1.style}\n\n大纲:\n${node_agent_outline.outline}"},
                "output_key": "draft"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_agent_editor",
            "type": "agentNode",
            "position": {"x": 1000, "y": 300},
            "data": {
                "label": "Code Reviewer - 文档审核",
                "agent_id": "preset-reviewer",
                "input_mapping": {"user_query": "审核以下文档的准确性、完整性和可读性，给出修改建议:\n\n${node_agent_writer.draft}"},
                "output_key": "review"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_template_1",
            "type": "templateNode",
            "position": {"x": 1300, "y": 300},
            "data": {
                "label": "格式化输出",
                "template": "# {{ topic }}\n\n{{ draft }}\n\n---\n\n## 审核意见\n{{ review }}\n\n*文档由 AI 自动生成*",
                "input_mapping": {
                    "topic": "${node_start_1.topic}",
                    "draft": "${node_agent_writer.draft}",
                    "review": "${node_agent_editor.review}"
                },
                "output_key": "final_doc"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_end_1",
            "type": "endNode",
            "position": {"x": 1600, "y": 300},
            "data": {
                "label": "输出文档",
                "output_mapping": {"document": "${node_template_1.final_doc}"}
            },
            "selected": False, "dragging": False
        }
    ],
    "edges_data": [
        {"id": "e1", "source": "node_start_1", "target": "node_agent_outline", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e2", "source": "node_agent_outline", "target": "node_agent_writer", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e3", "source": "node_agent_writer", "target": "node_agent_editor", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e4", "source": "node_agent_editor", "target": "node_template_1", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e5", "source": "node_template_1", "target": "node_end_1", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}}
    ]
}
```

### 3.4 模板 4：研究报告生成

```python
preset_template_4 = {
    "id": "00000000-0000-0000-0000-000000000004",
    "user_id": None,
    "workflow_id": None,
    "name": "研究报告生成",
    "description": "输入研究主题，自动进行网络搜索收集资料、知识检索补充背景信息，最后由 Agent 综合撰写研究报告。包含信息检索、分类整理、深度分析三个阶段。",
    "category": "研究分析",
    "thumbnail_url": "/static/templates/research-report.png",
    "use_count": 0,
    "is_preset": True,
    "nodes_data": [
        {
            "id": "node_start_1",
            "type": "startNode",
            "position": {"x": 100, "y": 300},
            "data": {
                "label": "研究主题",
                "inputs": [
                    {"name": "topic", "type": "string", "description": "研究主题", "required": True, "default_value": None},
                    {"name": "depth", "type": "string", "description": "研究深度(brief/detailed)", "required": False, "default_value": "detailed"}
                ],
                "outputs": [
                    {"name": "topic", "type": "string"},
                    {"name": "depth", "type": "string"}
                ]
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_classify_1",
            "type": "classifyNode",
            "position": {"x": 400, "y": 300},
            "data": {
                "label": "研究类型分类",
                "agent_id": "preset-pm",
                "input_mapping": {"text": "${node_start_1.topic}"},
                "categories": [
                    {"id": "cat_tech", "label": "技术研究", "keywords": ["技术", "框架", "API", "算法", "架构"]},
                    {"id": "cat_market", "label": "市场分析", "keywords": ["市场", "行业", "竞争", "趋势", "用户"]},
                    {"id": "cat_default", "label": "综合研究", "is_default": True}
                ]
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_agent_research_tech",
            "type": "agentNode",
            "position": {"x": 700, "y": 100},
            "data": {
                "label": "后端工程师 - 技术调研",
                "agent_id": "preset-backend",
                "input_mapping": {"user_query": "对以下技术主题进行深度调研，包括: 技术原理、核心特点、优劣势分析、实际应用场景、未来趋势。\n\n主题: ${node_start_1.topic}"},
                "output_key": "tech_research"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_agent_research_market",
            "type": "agentNode",
            "position": {"x": 700, "y": 300},
            "data": {
                "label": "产品经理 - 市场分析",
                "agent_id": "preset-pm",
                "input_mapping": {"user_query": "对以下主题进行市场分析，包括: 市场规模、主要玩家、竞争格局、发展趋势、机会与挑战。\n\n主题: ${node_start_1.topic}"},
                "output_key": "market_research"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_agent_research_general",
            "type": "agentNode",
            "position": {"x": 700, "y": 500},
            "data": {
                "label": "架构师 - 综合分析",
                "agent_id": "preset-architect",
                "input_mapping": {"user_query": "对以下主题进行全面研究分析: ${node_start_1.topic}"},
                "output_key": "general_research"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_aggregate_1",
            "type": "variableAggregateNode",
            "position": {"x": 1000, "y": 300},
            "data": {
                "label": "合并研究资料",
                "aggregations": [
                    {"name": "research_data", "sources": ["${node_agent_research_tech.tech_research}", "${node_agent_research_market.market_research}", "${node_agent_research_general.general_research}"], "mode": "array"}
                ],
                "output_key": "all_research"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_agent_writer",
            "type": "agentNode",
            "position": {"x": 1300, "y": 300},
            "data": {
                "label": "前端工程师 - 撰写报告",
                "agent_id": "preset-frontend",
                "input_mapping": {"user_query": "根据以下研究资料，撰写一份结构清晰、逻辑严密的研究报告（${node_start_1.depth}级别）:\n\n${node_aggregate_1.all_research}"},
                "output_key": "report"
            },
            "selected": False, "dragging": False
        },
        {
            "id": "node_end_1",
            "type": "endNode",
            "position": {"x": 1600, "y": 300},
            "data": {
                "label": "输出报告",
                "output_mapping": {"report": "${node_agent_writer.report}"}
            },
            "selected": False, "dragging": False
        }
    ],
    "edges_data": [
        {"id": "e1", "source": "node_start_1", "target": "node_classify_1", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e2", "source": "node_classify_1", "target": "node_agent_research_tech", "sourceHandle": "cat_tech", "targetHandle": "input_1", "type": "default", "animated": False, "label": "技术", "data": {"condition_branch_id": "cat_tech"}},
        {"id": "e3", "source": "node_classify_1", "target": "node_agent_research_market", "sourceHandle": "cat_market", "targetHandle": "input_1", "type": "default", "animated": False, "label": "市场", "data": {"condition_branch_id": "cat_market"}},
        {"id": "e4", "source": "node_classify_1", "target": "node_agent_research_general", "sourceHandle": "cat_default", "targetHandle": "input_1", "type": "default", "animated": False, "label": "综合", "data": {"condition_branch_id": "cat_default"}},
        {"id": "e5", "source": "node_agent_research_tech", "target": "node_aggregate_1", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e6", "source": "node_agent_research_market", "target": "node_aggregate_1", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e7", "source": "node_agent_research_general", "target": "node_aggregate_1", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e8", "source": "node_aggregate_1", "target": "node_agent_writer", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}},
        {"id": "e9", "source": "node_agent_writer", "target": "node_end_1", "sourceHandle": "output_1", "targetHandle": "input_1", "type": "default", "animated": False, "label": "", "data": {}}
    ]
}
```

### 3.5 预置分类列表

前端下拉选项中应使用的分类值（后端不做枚举限制，但种子数据统一使用）：

| 分类值 | 显示名 |
|--------|--------|
| `软件开发` | 软件开发 |
| `代码质量` | 代码质量 |
| `内容创作` | 内容创作 |
| `研究分析` | 研究分析 |

### 3.6 种子数据插入方式

在 Alembic 迁移文件中执行：

```python
from sqlalchemy import text

def upgrade():
    # ... 表结构变更 ...
    
    # 插入预置模板
    for tpl in [preset_template_1, preset_template_2, preset_template_3, preset_template_4]:
        op.execute(text("""
            INSERT INTO templates (id, user_id, workflow_id, name, description, category, 
                                   thumbnail_url, use_count, is_preset, nodes_data, edges_data, created_at)
            VALUES (:id, :user_id, :workflow_id, :name, :description, :category,
                    :thumbnail_url, :use_count, :is_preset, :nodes_data::jsonb, :edges_data::jsonb, NOW())
            ON CONFLICT DO NOTHING
        """).bindparams(
            id=tpl["id"],
            user_id=tpl["user_id"],
            workflow_id=tpl["workflow_id"],
            name=tpl["name"],
            description=tpl["description"],
            category=tpl["category"],
            thumbnail_url=tpl["thumbnail_url"],
            use_count=tpl["use_count"],
            is_preset=tpl["is_preset"],
            nodes_data=json.dumps(tpl["nodes_data"]),
            edges_data=json.dumps(tpl["edges_data"]),
        ))
```

---

## 4. API 完整规格

### 4.0 通用约定

#### 成功响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

#### 认证方式

所有接口需要：`Authorization: Bearer <access_token>`（预置模板的 GET 接口除外，详见各接口说明）

#### 权限模型

- 用户只能修改/删除自己创建的模板（`template.user_id == current_user.id`）
- 预置模板（`is_preset=True`）所有人可查看，但不可修改/删除
- 执行记录/日志只查看自己工作流的
- 环境变量只管理自己的

---

### 4.1 模板系统 API

#### 4.1.1 获取模板列表

**`GET /api/templates`**

**描述**：获取模板列表，支持搜索和分类筛选。预置模板和用户自定义模板混合展示。

**查询参数**：

```
page: int (default=1)
page_size: int (default=20, max=100)
keyword: string (可选, 模糊匹配 name 和 description)
category: string (可选, 精确匹配分类)
is_preset: bool (可选, 筛选预置/自定义)
sort_by: string (default="use_count", 可选: "name" | "created_at" | "use_count")
sort_order: string (default="desc", 可选: "asc" | "desc")
```

**业务逻辑**（`TemplateService.list_templates`）：

1. 构建基础查询：`SELECT * FROM templates`
2. 如有 `keyword`：`WHERE name ILIKE '%keyword%' OR description ILIKE '%keyword%'`
3. 如有 `category`：`AND category = :category`
4. 如有 `is_preset`：`AND is_preset = :is_preset`
5. 排序 + 分页
6. 对每条记录返回 `node_count = len(template.nodes_data) if nodes_data else 0`

**响应体**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "uuid",
        "name": "需求→开发→测试→上线 全流程",
        "description": "...",
        "category": "软件开发",
        "thumbnail_url": "/static/templates/full-cycle-dev.png",
        "use_count": 156,
        "node_count": 6,
        "is_preset": true,
        "created_at": "2026-07-15T10:00:00Z"
      }
    ],
    "total": 4,
    "page": 1,
    "page_size": 20,
    "has_next": false
  }
}
```

---

#### 4.1.2 获取模板详情

**`GET /api/templates/:id`**

**描述**：获取模板完整详情，包含 `nodes_data` 和 `edges_data`（画布快照数据）。

**业务逻辑**（`TemplateService.get_template`）：

1. 根据 `id` 查询模板
2. 不存在 → 404 `TEMPLATE_NOT_FOUND`
3. 返回完整数据

**响应体**：`TemplateDetailResponse`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": "uuid",
    "name": "...",
    "description": "...",
    "category": "软件开发",
    "thumbnail_url": "...",
    "use_count": 156,
    "is_preset": true,
    "nodes_data": [...],
    "edges_data": [...],
    "created_at": "2026-07-15T10:00:00Z"
  }
}
```

---

#### 4.1.3 从工作流保存为模板

**`POST /api/workflows/:id/save-as-template`**

**描述**：将指定工作流的当前画布数据保存为新模板。

**请求体**：

```json
{
  "name": "我的自定义模板",
  "description": "这是一个从工作流保存的模板",
  "category": "自定义",
  "thumbnail_url": null
}
```

**Pydantic Schema**：

```python
class SaveAsTemplateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    category: str = Field(default="自定义", max_length=100)
    thumbnail_url: Optional[str] = None
```

**业务逻辑**（`TemplateService.save_as_template`）：

1. 查询工作流 + 权限检查（`workflow.user_id == current_user.id`）
2. 复制工作流的 `nodes_data` 和 `edges_data` 到模板
3. 创建模板记录：
   - `user_id = current_user.id`
   - `workflow_id = workflow.id`（记录来源，可选）
   - `is_preset = False`
4. 返回新模板详情

**响应体**：`TemplateDetailResponse`

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `WORKFLOW_NOT_FOUND` | 工作流不存在 |
| 403 | `FORBIDDEN` | 无权操作此工作流 |

---

#### 4.1.4 使用模板创建工作流

**`POST /api/templates/:id/use`**

**描述**：基于模板创建一个新的工作流。复制模板的 `nodes_data` 和 `edges_data` 到新工作流，并递增模板的 `use_count`。

**请求体**：

```json
{
  "name": null
}
```

- `name` 可选，不传则使用模板名称（后加 " - 副本"）

**Pydantic Schema**：

```python
class UseTemplateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
```

**业务逻辑**（`TemplateService.use_template`）：

1. 查询模板，不存在 → 404 `TEMPLATE_NOT_FOUND`
2. 确定新工作流名称：`name or f"{template.name} - 副本"`
3. 调用 `WorkflowService.create_workflow()` 创建工作流：
   - `user_id = current_user.id`
   - `name = 工作流名称`
   - `nodes_data = template.nodes_data`（深拷贝）
   - `edges_data = template.edges_data`（深拷贝）
4. 递增模板 `use_count += 1`
5. 返回新创建的工作流详情

**响应体**：`WorkflowDetailResponse`

---

#### 4.1.5 删除模板

**`DELETE /api/templates/:id`**

**描述**：删除自定义模板。预置模板不可删除。

**业务逻辑**（`TemplateService.delete_template`）：

1. 查询模板，不存在 → 404 `TEMPLATE_NOT_FOUND`
2. 检查 `is_preset`：若为 `True` → 403 `PRESET_TEMPLATE_PROTECTED`
3. 检查权限：`template.user_id != current_user.id` → 403 `FORBIDDEN`
4. 删除模板记录
5. 返回删除确认

**响应体**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "模板已删除",
    "template_id": "uuid"
  }
}
```

---

### 4.2 版本管理增强 API

#### 4.2.1 手动打标签

**`POST /api/workflows/:id/versions/:ver/tag`**

**描述**：为指定版本添加/更新标签（如 "稳定版"、"上线版"）。

**请求体**：

```json
{
  "tag": "稳定版 v2.0"
}
```

**Pydantic Schema**：

```python
class TagVersionRequest(BaseModel):
    tag: str = Field(..., min_length=1, max_length=100)
```

**业务逻辑**（`VersionService.tag_version`）：

1. 查询工作流 + 权限检查
2. 查询目标版本（`workflow_id = :id AND version_number = :ver`）
3. 版本不存在 → 404 `VERSION_NOT_FOUND`
4. 更新 `version.tag = request.tag`
5. 返回更新后的版本信息

**响应体**：`WorkflowVersionResponse`

---

#### 4.2.2 删除标签

**`DELETE /api/workflows/:id/versions/:ver/tag`**

**描述**：移除指定版本的标签。

**业务逻辑**（`VersionService.remove_tag`）：

1. 查询工作流 + 权限检查
2. 查询目标版本
3. 版本不存在 → 404 `VERSION_NOT_FOUND`
4. 若无标签 → 400 `NO_TAG_TO_REMOVE`
5. 设置 `version.tag = None`
6. 返回更新后的版本信息

**响应体**：`WorkflowVersionResponse`

---

#### 4.2.3 版本对比（增强）

**`GET /api/workflows/:id/versions/diff?v1=:v1&v2=:v2`**

**描述**：对比两个版本的差异。此接口在 Phase 4 已定义，Phase 6 增强 Diff 算法（详见第 6 章）。

**响应体**：`VersionDiffResponse`（增强版）

```json
{
  "v1": 2,
  "v2": 5,
  "added_nodes": [
    {"id": "node_new_1", "type": "codeNode", "label": "新增代码节点", "position": {"x": 500, "y": 300}}
  ],
  "removed_nodes": [
    {"id": "node_old_1", "type": "httpNode", "label": "被删除的HTTP节点"}
  ],
  "modified_nodes": [
    {
      "id": "node_agent_1",
      "type": "agentNode",
      "label": "修改了Agent节点",
      "changes": [
        {"field": "data.agent_id", "old_value": "agent-uuid-1", "new_value": "agent-uuid-2"},
        {"field": "data.temperature", "old_value": 0.7, "new_value": 1.0}
      ]
    }
  ],
  "added_edges": [
    {"id": "e_new", "source": "node_start_1", "target": "node_new_1"}
  ],
  "removed_edges": [
    {"id": "e_old", "source": "node_old_1", "target": "node_end_1"}
  ],
  "modified_edges": [
    {"id": "e1", "source": "node_start_1", "old_target": "node_agent_1", "new_target": "node_new_1"}
  ]
}
```

#### 4.2.4 版本预览（复用 Phase 4）

**`GET /api/workflows/:id/versions/:ver`**

已在 Phase 4 实现。返回指定版本的完整数据（`nodes_data` + `edges_data`），前端以只读模式渲染画布。Phase 6 无需修改。

---

### 4.3 执行历史 API

#### 4.3.1 获取执行历史列表

**`GET /api/executions`**

**描述**：获取当前用户的执行历史列表，支持分页和多维度筛选。

**查询参数**：

```
page: int (default=1)
page_size: int (default=20, max=100)
workflow_id: uuid (可选, 按工作流筛选)
status: string (可选, 按状态筛选: pending | running | success | failed | paused | cancelled)
start_time: datetime (可选, RFC3339 格式, 起始时间)
end_time: datetime (可选, RFC3339 格式, 结束时间)
```

**业务逻辑**（`ExecutionService.list_executions`）：

1. 构建查询：`JOIN workflows ON executions.workflow_id = workflows.id WHERE workflows.user_id = :current_user_id`
2. 可选筛选条件：
   - `workflow_id`：`AND executions.workflow_id = :workflow_id`
   - `status`：`AND executions.status = :status`
   - `start_time`：`AND executions.started_at >= :start_time`
   - `end_time`：`AND executions.started_at <= :end_time`
3. 按 `started_at DESC` 排序
4. 分页查询
5. 关联查询工作流名称 `workflow.name`

**响应体**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "uuid",
        "workflow_id": "uuid",
        "workflow_name": "我的RAG工作流",
        "version_number": 3,
        "status": "success",
        "total_duration_ms": 12500,
        "total_tokens": 3200,
        "total_cost": 0.012800,
        "started_at": "2026-07-15T10:00:00Z",
        "finished_at": "2026-07-15T10:00:12Z",
        "node_count": 5,
        "success_node_count": 5,
        "failed_node_count": 0
      }
    ],
    "total": 42,
    "page": 1,
    "page_size": 20,
    "has_next": true
  }
}
```

---

#### 4.3.2 获取执行详情

**`GET /api/executions/:id`**

**描述**：获取某次执行的完整详情，包含所有节点执行记录和关联日志摘要。

**业务逻辑**（`ExecutionService.get_execution`）：

1. 查询执行记录
2. 关联查询工作流，验证 `workflow.user_id == current_user.id`
3. 查询所有 `ExecutionNode`（按 `started_at ASC` 排序）
4. 统计汇总：
   - `node_stats`：各状态节点计数
   - `total_tokens`：所有节点 `tokens_used` 之和
   - `total_duration_ms`：所有节点 `duration_ms` 之和
   - `success_rate`：成功节点数 / 总节点数

**响应体**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": "uuid",
    "workflow_id": "uuid",
    "workflow_name": "我的RAG工作流",
    "version_number": 3,
    "status": "success",
    "input_data": {"user_query": "什么是向量数据库"},
    "output_data": {"final_answer": "..."},
    "total_duration_ms": 12500,
    "total_tokens": 3200,
    "total_cost": 0.012800,
    "started_at": "2026-07-15T10:00:00Z",
    "finished_at": "2026-07-15T10:00:12Z",
    "nodes": [
      {
        "id": "uuid",
        "node_id": "node_start_1",
        "node_type": "startNode",
        "status": "success",
        "input_data": {"user_query": "什么是向量数据库"},
        "output_data": {"user_query": "什么是向量数据库"},
        "duration_ms": 5,
        "tokens_used": 0,
        "error_message": null,
        "started_at": "2026-07-15T10:00:00Z",
        "finished_at": "2026-07-15T10:00:00Z"
      },
      {
        "id": "uuid",
        "node_id": "node_kb_1",
        "node_type": "knowledgeRetrievalNode",
        "status": "success",
        "input_data": {"query": "什么是向量数据库"},
        "output_data": {"results": [...]},
        "duration_ms": 3500,
        "tokens_used": 800,
        "error_message": null,
        "started_at": "2026-07-15T10:00:01Z",
        "finished_at": "2026-07-15T10:00:04Z"
      }
    ],
    "node_stats": {
      "total": 5,
      "success": 5,
      "failed": 0,
      "skipped": 0,
      "pending": 0,
      "running": 0,
      "paused": 0
    },
    "success_rate": 1.0,
    "log_count": 12
  }
}
```

---

#### 4.3.3 执行统计

**`GET /api/executions/stats`**

**描述**：获取执行统计聚合数据，用于 Dashboard 展示。

**查询参数**：

```
workflow_id: uuid (可选, 按工作流筛选)
period: string (default="7d", 可选: "7d" | "30d" | "90d")
```

**业务逻辑**（`ExecutionService.get_stats`）：

1. 计算时间范围：`now() - period` 到 `now()`
2. 执行聚合查询：

```sql
-- 总体统计
SELECT
  COUNT(*) as total_executions,
  COUNT(*) FILTER (WHERE status = 'success') as success_count,
  COUNT(*) FILTER (WHERE status = 'failed') as failed_count,
  AVG(total_duration_ms) FILTER (WHERE status = 'success') as avg_duration_ms,
  SUM(total_tokens) as total_tokens,
  SUM(total_cost) as total_cost
FROM executions e
JOIN workflows w ON e.workflow_id = w.id
WHERE w.user_id = :user_id
  AND e.started_at >= :start_time

-- 按天统计（用于趋势图）
SELECT
  DATE(started_at) as date,
  COUNT(*) as count,
  COUNT(*) FILTER (WHERE status = 'success') as success_count,
  AVG(total_duration_ms) FILTER (WHERE status = 'success') as avg_duration_ms
FROM executions e
JOIN workflows w ON e.workflow_id = w.id
WHERE w.user_id = :user_id
  AND e.started_at >= :start_time
GROUP BY DATE(started_at)
ORDER BY date

-- 按工作流统计（可选，当不传 workflow_id 时）
SELECT
  w.id as workflow_id,
  w.name as workflow_name,
  COUNT(*) as execution_count,
  COUNT(*) FILTER (WHERE e.status = 'success') as success_count,
  AVG(e.total_duration_ms) FILTER (WHERE e.status = 'success') as avg_duration_ms
FROM executions e
JOIN workflows w ON e.workflow_id = w.id
WHERE w.user_id = :user_id
  AND e.started_at >= :start_time
GROUP BY w.id, w.name
ORDER BY execution_count DESC
LIMIT 10
```

**响应体**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "summary": {
      "total_executions": 156,
      "success_count": 142,
      "failed_count": 14,
      "success_rate": 0.91,
      "avg_duration_ms": 8500,
      "total_tokens": 125000,
      "total_cost": 0.523400
    },
    "daily_trend": [
      {"date": "2026-07-09", "count": 18, "success_count": 16, "avg_duration_ms": 7200},
      {"date": "2026-07-10", "count": 25, "success_count": 23, "avg_duration_ms": 9100}
    ],
    "by_workflow": [
      {
        "workflow_id": "uuid",
        "workflow_name": "RAG工作流",
        "execution_count": 45,
        "success_count": 42,
        "avg_duration_ms": 6800
      }
    ]
  }
}
```

---

### 4.4 日志中心 API

#### 4.4.1 获取日志列表

**`GET /api/logs`**

**描述**：获取全局日志列表，支持分页、筛选和全文搜索。

**查询参数**：

```
page: int (default=1)
page_size: int (default=50, max=200)
level: string (可选, 按级别筛选: info | warn | error)
execution_id: uuid (可选, 按执行记录筛选)
node_id: string (可选, 按节点ID筛选)
start_time: datetime (可选, RFC3339)
end_time: datetime (可选, RFC3339)
search: string (可选, 全文搜索 message 字段)
```

**业务逻辑**（`LogService.list_logs`）：

1. 构建查询：`JOIN executions ON logs.execution_id = executions.id JOIN workflows ON executions.workflow_id = workflows.id WHERE workflows.user_id = :current_user_id`
2. 可选筛选：
   - `level`：`AND logs.level = :level`
   - `execution_id`：`AND logs.execution_id = :execution_id`
   - `node_id`：`AND logs.node_id = :node_id`
   - `start_time` / `end_time`：`AND logs.timestamp >= :start_time AND logs.timestamp <= :end_time`
   - `search`：`AND logs.message ILIKE '%search%'`（使用 pg_trgm 索引加速）
3. 按 `timestamp DESC` 排序
4. 分页查询

**响应体**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "uuid",
        "execution_id": "uuid",
        "workflow_name": "RAG工作流",
        "level": "info",
        "message": "开始执行知识检索节点",
        "node_id": "node_kb_1",
        "node_type": "knowledgeRetrievalNode",
        "timestamp": "2026-07-15T10:00:01Z"
      },
      {
        "id": "uuid",
        "execution_id": "uuid",
        "workflow_name": "RAG工作流",
        "level": "error",
        "message": "Agent 调用失败: API rate limit exceeded",
        "node_id": "node_agent_1",
        "node_type": "agentNode",
        "timestamp": "2026-07-15T10:00:05Z"
      }
    ],
    "total": 1250,
    "page": 1,
    "page_size": 50,
    "has_next": true
  }
}
```

---

#### 4.4.2 获取日志详情

**`GET /api/logs/:id`**

**描述**：获取单条日志的完整信息。

**业务逻辑**（`LogService.get_log`）：

1. 查询日志记录
2. 关联验证权限（通过 execution → workflow → user_id）
3. 不存在 → 404 `LOG_NOT_FOUND`
4. 无权限 → 403

**响应体**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": "uuid",
    "execution_id": "uuid",
    "workflow_id": "uuid",
    "workflow_name": "RAG工作流",
    "level": "error",
    "message": "Agent 调用失败: API rate limit exceeded",
    "node_id": "node_agent_1",
    "node_type": "agentNode",
    "timestamp": "2026-07-15T10:00:05Z",
    "metadata": {
      "agent_id": "uuid",
      "model": "gpt-4",
      "retry_count": 3,
      "stack_trace": "..."
    }
  }
}
```

> 注意：Phase 0 的 Log 模型没有 `metadata` 字段。Phase 6 **不新增**此字段。日志详情中的 `metadata` 字段留空 `{}` 即可。如需后续扩展，可在 Phase 7 增加 JSONB 的 `metadata` 列。

---

### 4.5 环境变量管理 API

#### 4.5.1 获取环境变量列表

**`GET /api/env-vars`**

**描述**：获取当前用户的所有环境变量。Secret 类型的值永远脱敏显示。

**查询参数**：

```
page: int (default=1)
page_size: int (default=50, max=100)
type: string (可选, 按类型筛选: string | secret)
```

**业务逻辑**（`EnvService.list_env_vars`）：

1. 查询 `WHERE user_id = :current_user_id`
2. 可选筛选 `AND type = :type`
3. 排序：按 `key ASC`
4. 分页查询
5. 对 Secret 类型，值的显示为 `****{last4}`（最后4位）

**响应体**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "uuid",
        "key": "OPENAI_API_KEY",
        "type": "secret",
        "masked_value": "****sk-xyZ9",
        "created_at": "2026-07-10T08:00:00Z",
        "updated_at": "2026-07-12T15:30:00Z"
      },
      {
        "id": "uuid",
        "key": "DATABASE_URL",
        "type": "string",
        "value": "postgresql://localhost:5432/mydb",
        "created_at": "2026-07-11T10:00:00Z",
        "updated_at": "2026-07-11T10:00:00Z"
      }
    ],
    "total": 2,
    "page": 1,
    "page_size": 50,
    "has_next": false
  }
}
```

**注意**：
- `string` 类型返回明文 `value` 字段
- `secret` 类型返回 `masked_value` 字段（不返回 `value` 字段）

---

#### 4.5.2 创建环境变量

**`POST /api/env-vars`**

**描述**：创建新的环境变量。

**请求体**：

```json
{
  "key": "OPENAI_API_KEY",
  "value": "sk-xxxxxxxxxxxx",
  "type": "secret"
}
```

**Pydantic Schema**：

```python
class EnvVarCreateRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=255, pattern=r"^[A-Z0-9_]+$")
    value: str = Field(..., min_length=1, max_length=10000)
    type: str = Field(default="string", pattern="^(string|secret)$")
```

**业务逻辑**（`EnvService.create_env_var`）：

1. 校验 `key` 格式：只允许大写字母 + 数字 + 下划线（`^[A-Z0-9_]+$`）
2. 检查唯一性：`WHERE user_id = :user_id AND key = :key`
   - 已存在 → 409 `ENV_VAR_KEY_EXISTS`
3. 加密值：
   - `secret` 类型：使用 Fernet 加密
   - `string` 类型：直接存储（或也用 Fernet，统一处理）
4. 创建记录：`value_encrypted = encrypted_value`
5. 返回创建后的变量信息（Secret 类型脱敏）

**响应体**：`EnvVarResponse`

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 409 | `ENV_VAR_KEY_EXISTS` | 变量名已存在 |
| 422 | `VALIDATION_ERROR` | key 格式不合法 |

---

#### 4.5.3 更新环境变量

**`PUT /api/env-vars/:id`**

**描述**：更新环境变量。Secret 类型必须重新输入完整值。

**请求体**：

```json
{
  "value": "sk-newkey-xxxxxxxx",
  "type": "secret"
}
```

**Pydantic Schema**：

```python
class EnvVarUpdateRequest(BaseModel):
    value: Optional[str] = Field(default=None, min_length=1, max_length=10000)
    type: Optional[str] = Field(default=None, pattern="^(string|secret)$")
```

**业务逻辑**（`EnvService.update_env_var`）：

1. 查询环境变量 + 权限检查（`env_var.user_id == current_user.id`）
2. 不存在 → 404 `ENV_VAR_NOT_FOUND`
3. 如果更新 `type`：不允许从 `string` 改为 `secret` 或反之（禁止修改类型）→ 400 `ENV_VAR_TYPE_IMMUTABLE`
4. 如果更新 `value`：
   - 重新加密并存储
   - `updated_at = now()`
5. 返回更新后的变量信息（Secret 类型脱敏）

**响应体**：`EnvVarResponse`

---

#### 4.5.4 删除环境变量

**`DELETE /api/env-vars/:id`**

**描述**：删除环境变量。

**业务逻辑**（`EnvService.delete_env_var`）：

1. 查询环境变量 + 权限检查
2. 不存在 → 404 `ENV_VAR_NOT_FOUND`
3. 删除记录
4. 返回删除确认

**响应体**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "环境变量已删除",
    "env_var_id": "uuid"
  }
}
```

---

## 5. Service 层设计

### 5.1 TemplateService

```python
# app/services/template_service.py

import uuid
import copy
from typing import Optional
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import Template
from app.models.workflow import Workflow
from app.core.exceptions import AppException


class TemplateService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_templates(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        is_preset: Optional[bool] = None,
        sort_by: str = "use_count",
        sort_order: str = "desc",
    ) -> dict:
        """获取模板列表"""
        query = select(Template)
        count_query = select(func.count(Template.id))

        # 筛选
        if keyword:
            like_pattern = f"%{keyword}%"
            condition = or_(
                Template.name.ilike(like_pattern),
                Template.description.ilike(like_pattern),
            )
            query = query.where(condition)
            count_query = count_query.where(condition)

        if category:
            query = query.where(Template.category == category)
            count_query = count_query.where(Template.category == category)

        if is_preset is not None:
            query = query.where(Template.is_preset == is_preset)
            count_query = count_query.where(Template.is_preset == is_preset)

        # 排序
        sort_column = getattr(Template, sort_by, Template.use_count)
        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # 分页
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        offset = (page - 1) * page_size
        result = await self.db.execute(query.offset(offset).limit(page_size))
        templates = result.scalars().all()

        items = []
        for tpl in templates:
            items.append({
                "id": tpl.id,
                "name": tpl.name,
                "description": tpl.description,
                "category": tpl.category,
                "thumbnail_url": tpl.thumbnail_url,
                "use_count": tpl.use_count,
                "node_count": len(tpl.nodes_data) if tpl.nodes_data else 0,
                "is_preset": tpl.is_preset,
                "created_at": tpl.created_at,
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": offset + page_size < total,
        }

    async def get_template(self, template_id: uuid.UUID) -> Template:
        """获取模板详情"""
        result = await self.db.execute(
            select(Template).where(Template.id == template_id)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise TemplateNotFoundError()
        return template

    async def save_as_template(
        self,
        workflow_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        description: Optional[str] = None,
        category: str = "自定义",
        thumbnail_url: Optional[str] = None,
    ) -> Template:
        """从工作流保存为模板"""
        # 查询工作流 + 权限检查
        result = await self.db.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise WorkflowNotFoundError()
        if workflow.user_id != user_id:
            raise ForbiddenError()

        # 创建模板（深拷贝画布数据）
        template = Template(
            user_id=user_id,
            workflow_id=workflow.id,
            name=name,
            description=description,
            category=category,
            thumbnail_url=thumbnail_url,
            nodes_data=copy.deepcopy(workflow.nodes_data) if workflow.nodes_data else [],
            edges_data=copy.deepcopy(workflow.edges_data) if workflow.edges_data else [],
            is_preset=False,
            use_count=0,
        )
        self.db.add(template)
        await self.db.flush()
        return template

    async def use_template(
        self,
        template_id: uuid.UUID,
        user_id: uuid.UUID,
        name_override: Optional[str] = None,
    ) -> dict:
        """使用模板创建工作流"""
        template = await self.get_template(template_id)

        # 确定工作流名称
        name = name_override or f"{template.name} - 副本"

        # 创建工作流（通过 WorkflowService）
        from app.services.workflow_service import WorkflowService
        workflow_service = WorkflowService(self.db)
        workflow = await workflow_service.create_workflow(
            user_id=user_id,
            name=name,
            description=f"从模板「{template.name}」创建",
            nodes_data=copy.deepcopy(template.nodes_data) if template.nodes_data else [],
            edges_data=copy.deepcopy(template.edges_data) if template.edges_data else [],
        )

        # 递增使用次数
        template.use_count += 1
        await self.db.flush()

        return workflow

    async def delete_template(self, template_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """删除自定义模板"""
        template = await self.get_template(template_id)

        if template.is_preset:
            raise PresetTemplateProtectedError()
        if template.user_id != user_id:
            raise ForbiddenError()

        await self.db.delete(template)
        await self.db.flush()
```

---

### 5.2 VersionService 增强

```python
# app/services/version_service.py — Phase 6 增强部分

class VersionService:
    # ... Phase 4 已有方法（create_version, list_versions, get_version, rollback_to_version, diff_versions）...

    async def tag_version(
        self,
        workflow_id: uuid.UUID,
        version_number: int,
        tag: str,
        user_id: uuid.UUID,
    ) -> dict:
        """为版本打标签"""
        # 权限检查
        workflow = await self._get_workflow_with_auth(workflow_id, user_id)

        # 查询版本
        version = await self._get_version(workflow_id, version_number)
        if not version:
            raise VersionNotFoundError(version_number)

        version.tag = tag
        await self.db.flush()

        return {
            "id": version.id,
            "workflow_id": version.workflow_id,
            "version_number": version.version_number,
            "tag": version.tag,
            "node_count": len(version.nodes_data) if version.nodes_data else 0,
            "created_at": version.created_at,
        }

    async def remove_tag(
        self,
        workflow_id: uuid.UUID,
        version_number: int,
        user_id: uuid.UUID,
    ) -> dict:
        """删除版本标签"""
        workflow = await self._get_workflow_with_auth(workflow_id, user_id)
        version = await self._get_version(workflow_id, version_number)
        if not version:
            raise VersionNotFoundError(version_number)
        if version.tag is None:
            raise NoTagToRemoveError()

        version.tag = None
        await self.db.flush()

        return {
            "id": version.id,
            "workflow_id": version.workflow_id,
            "version_number": version.version_number,
            "tag": version.tag,
            "node_count": len(version.nodes_data) if version.nodes_data else 0,
            "created_at": version.created_at,
        }

    async def _get_workflow_with_auth(self, workflow_id: uuid.UUID, user_id: uuid.UUID):
        """查询工作流并验证权限（内部辅助方法）"""
        result = await self.db.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise WorkflowNotFoundError()
        if workflow.user_id != user_id:
            raise ForbiddenError()
        return workflow

    async def _get_version(self, workflow_id: uuid.UUID, version_number: int):
        """查询指定版本（内部辅助方法）"""
        result = await self.db.execute(
            select(WorkflowVersion).where(
                WorkflowVersion.workflow_id == workflow_id,
                WorkflowVersion.version_number == version_number,
            )
        )
        return result.scalar_one_or_none()
```

---

### 5.3 ExecutionService

```python
# app/services/execution_service.py

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, case, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import Execution, ExecutionNode
from app.models.workflow import Workflow


class ExecutionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_executions(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        workflow_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> dict:
        """获取执行历史列表"""
        # 基础查询：关联工作流以获取名称和验证权限
        query = (
            select(Execution, Workflow.name.label("workflow_name"))
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(Workflow.user_id == user_id)
        )
        count_query = (
            select(func.count(Execution.id))
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(Workflow.user_id == user_id)
        )

        # 筛选
        if workflow_id:
            query = query.where(Execution.workflow_id == workflow_id)
            count_query = count_query.where(Execution.workflow_id == workflow_id)
        if status:
            query = query.where(Execution.status == status)
            count_query = count_query.where(Execution.status == status)
        if start_time:
            query = query.where(Execution.started_at >= start_time)
            count_query = count_query.where(Execution.started_at >= start_time)
        if end_time:
            query = query.where(Execution.started_at <= end_time)
            count_query = count_query.where(Execution.started_at <= end_time)

        # 排序
        query = query.order_by(Execution.started_at.desc())

        # 分页
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        offset = (page - 1) * page_size
        result = await self.db.execute(query.offset(offset).limit(page_size))
        rows = result.all()

        items = []
        for execution, workflow_name in rows:
            # 统计节点数
            node_stats_result = await self.db.execute(
                select(
                    func.count(ExecutionNode.id),
                    func.count(ExecutionNode.id).filter(ExecutionNode.status == "success"),
                    func.count(ExecutionNode.id).filter(ExecutionNode.status == "failed"),
                ).where(ExecutionNode.execution_id == execution.id)
            )
            node_total, node_success, node_failed = node_stats_result.one()

            items.append({
                "id": execution.id,
                "workflow_id": execution.workflow_id,
                "workflow_name": workflow_name,
                "version_number": execution.version_number,
                "status": execution.status.value if hasattr(execution.status, 'value') else execution.status,
                "total_duration_ms": execution.total_duration_ms,
                "total_tokens": execution.total_tokens,
                "total_cost": float(execution.total_cost) if execution.total_cost else None,
                "started_at": execution.started_at,
                "finished_at": execution.finished_at,
                "node_count": node_total,
                "success_node_count": node_success,
                "failed_node_count": node_failed,
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": offset + page_size < total,
        }

    async def get_execution(self, execution_id: uuid.UUID, user_id: uuid.UUID) -> dict:
        """获取执行详情"""
        # 查询执行记录 + 工作流名称
        result = await self.db.execute(
            select(Execution, Workflow.name.label("workflow_name"))
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(Execution.id == execution_id)
        )
        row = result.one_or_none()
        if not row:
            raise ExecutionNotFoundError()
        execution, workflow_name = row

        # 权限检查
        wf_result = await self.db.execute(
            select(Workflow.user_id).where(Workflow.id == execution.workflow_id)
        )
        wf_user_id = wf_result.scalar()
        if wf_user_id != user_id:
            raise ForbiddenError()

        # 查询所有节点执行记录
        nodes_result = await self.db.execute(
            select(ExecutionNode)
            .where(ExecutionNode.execution_id == execution_id)
            .order_by(ExecutionNode.started_at.asc())
        )
        nodes = nodes_result.scalars().all()

        # 节点统计
        stats = {"total": 0, "success": 0, "failed": 0, "skipped": 0, "pending": 0, "running": 0, "paused": 0}
        for node in nodes:
            stats["total"] += 1
            status_val = node.status.value if hasattr(node.status, 'value') else node.status
            if status_val in stats:
                stats[status_val] += 1

        success_rate = stats["success"] / stats["total"] if stats["total"] > 0 else 0.0

        return {
            "id": execution.id,
            "workflow_id": execution.workflow_id,
            "workflow_name": workflow_name,
            "version_number": execution.version_number,
            "status": execution.status.value if hasattr(execution.status, 'value') else execution.status,
            "input_data": execution.input_data,
            "output_data": execution.output_data,
            "total_duration_ms": execution.total_duration_ms,
            "total_tokens": execution.total_tokens,
            "total_cost": float(execution.total_cost) if execution.total_cost else None,
            "started_at": execution.started_at,
            "finished_at": execution.finished_at,
            "nodes": [
                {
                    "id": n.id,
                    "node_id": n.node_id,
                    "node_type": n.node_type,
                    "status": n.status.value if hasattr(n.status, 'value') else n.status,
                    "input_data": n.input_data,
                    "output_data": n.output_data,
                    "duration_ms": n.duration_ms,
                    "tokens_used": n.tokens_used,
                    "error_message": n.error_message,
                    "started_at": n.started_at,
                    "finished_at": n.finished_at,
                }
                for n in nodes
            ],
            "node_stats": stats,
            "success_rate": round(success_rate, 2),
        }

    async def get_stats(
        self,
        user_id: uuid.UUID,
        period: str = "7d",
        workflow_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """获取执行统计"""
        # 计算时间范围
        now = datetime.now(timezone.utc)
        period_map = {"7d": 7, "30d": 30, "90d": 90}
        days = period_map.get(period, 7)
        start_time = now - timedelta(days=days)

        # 基础筛选条件
        base_filter = and_(
            Workflow.user_id == user_id,
            Execution.started_at >= start_time,
        )
        if workflow_id:
            base_filter = and_(base_filter, Execution.workflow_id == workflow_id)

        # 总体统计
        summary_query = (
            select(
                func.count(Execution.id).label("total"),
                func.count(Execution.id).filter(Execution.status == "success").label("success"),
                func.count(Execution.id).filter(Execution.status == "failed").label("failed"),
                func.avg(Execution.total_duration_ms).filter(Execution.status == "success").label("avg_duration"),
                func.coalesce(func.sum(Execution.total_tokens), 0).label("total_tokens"),
                func.coalesce(func.sum(Execution.total_cost), 0).label("total_cost"),
            )
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(base_filter)
        )
        summary_result = await self.db.execute(summary_query)
        summary_row = summary_result.one()

        total = summary_row.total or 0
        success = summary_row.success or 0
        summary = {
            "total_executions": total,
            "success_count": success,
            "failed_count": summary_row.failed or 0,
            "success_rate": round(success / total, 2) if total > 0 else 0.0,
            "avg_duration_ms": round(summary_row.avg_duration or 0),
            "total_tokens": int(summary_row.total_tokens),
            "total_cost": float(summary_row.total_cost),
        }

        # 按天趋势
        daily_query = (
            select(
                func.date(Execution.started_at).label("date"),
                func.count(Execution.id).label("count"),
                func.count(Execution.id).filter(Execution.status == "success").label("success_count"),
                func.avg(Execution.total_duration_ms).filter(Execution.status == "success").label("avg_duration"),
            )
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(base_filter)
            .group_by(func.date(Execution.started_at))
            .order_by(func.date(Execution.started_at))
        )
        daily_result = await self.db.execute(daily_query)
        daily_trend = [
            {
                "date": str(row.date),
                "count": row.count,
                "success_count": row.success_count or 0,
                "avg_duration_ms": round(row.avg_duration or 0),
            }
            for row in daily_result.all()
        ]

        # 按工作流统计
        by_wf_query = (
            select(
                Workflow.id.label("workflow_id"),
                Workflow.name.label("workflow_name"),
                func.count(Execution.id).label("count"),
                func.count(Execution.id).filter(Execution.status == "success").label("success_count"),
                func.avg(Execution.total_duration_ms).filter(Execution.status == "success").label("avg_duration"),
            )
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(and_(Workflow.user_id == user_id, Execution.started_at >= start_time))
            .group_by(Workflow.id, Workflow.name)
            .order_by(func.count(Execution.id).desc())
            .limit(10)
        )
        by_wf_result = await self.db.execute(by_wf_query)
        by_workflow = [
            {
                "workflow_id": str(row.workflow_id),
                "workflow_name": row.workflow_name,
                "execution_count": row.count,
                "success_count": row.success_count or 0,
                "avg_duration_ms": round(row.avg_duration or 0),
            }
            for row in by_wf_result.all()
        ]

        return {
            "summary": summary,
            "daily_trend": daily_trend,
            "by_workflow": by_workflow,
        }
```

---

### 5.4 LogService

```python
# app/services/log_service.py

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import Execution, Log
from app.models.workflow import Workflow


class LogService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_logs(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
        level: Optional[str] = None,
        execution_id: Optional[uuid.UUID] = None,
        node_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        search: Optional[str] = None,
    ) -> dict:
        """获取日志列表"""
        # 多表关联：logs → executions → workflows
        query = (
            select(Log, Workflow.name.label("workflow_name"))
            .join(Execution, Log.execution_id == Execution.id)
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(Workflow.user_id == user_id)
        )
        count_query = (
            select(func.count(Log.id))
            .join(Execution, Log.execution_id == Execution.id)
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(Workflow.user_id == user_id)
        )

        # 筛选
        if level:
            query = query.where(Log.level == level)
            count_query = count_query.where(Log.level == level)
        if execution_id:
            query = query.where(Log.execution_id == execution_id)
            count_query = count_query.where(Log.execution_id == execution_id)
        if node_id:
            query = query.where(Log.node_id == node_id)
            count_query = count_query.where(Log.node_id == node_id)
        if start_time:
            query = query.where(Log.timestamp >= start_time)
            count_query = count_query.where(Log.timestamp >= start_time)
        if end_time:
            query = query.where(Log.timestamp <= end_time)
            count_query = count_query.where(Log.timestamp <= end_time)
        if search:
            like_pattern = f"%{search}%"
            query = query.where(Log.message.ilike(like_pattern))
            count_query = count_query.where(Log.message.ilike(like_pattern))

        # 排序
        query = query.order_by(Log.timestamp.desc())

        # 分页
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        offset = (page - 1) * page_size
        result = await self.db.execute(query.offset(offset).limit(page_size))
        rows = result.all()

        items = []
        for log, workflow_name in rows:
            items.append({
                "id": log.id,
                "execution_id": log.execution_id,
                "workflow_name": workflow_name,
                "level": log.level.value if hasattr(log.level, 'value') else log.level,
                "message": log.message,
                "node_id": log.node_id,
                "timestamp": log.timestamp,
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": offset + page_size < total,
        }

    async def get_log(self, log_id: uuid.UUID, user_id: uuid.UUID) -> dict:
        """获取日志详情"""
        result = await self.db.execute(
            select(Log, Workflow.name.label("workflow_name"), Workflow.id.label("workflow_id"))
            .join(Execution, Log.execution_id == Execution.id)
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(Log.id == log_id)
        )
        row = result.one_or_none()
        if not row:
            raise LogNotFoundError()
        log, workflow_name, workflow_id = row

        # 权限检查
        wf_result = await self.db.execute(
            select(Workflow.user_id).where(Workflow.id == workflow_id)
        )
        if wf_result.scalar() != user_id:
            raise ForbiddenError()

        return {
            "id": log.id,
            "execution_id": log.execution_id,
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "level": log.level.value if hasattr(log.level, 'value') else log.level,
            "message": log.message,
            "node_id": log.node_id,
            "timestamp": log.timestamp,
            "metadata": {},
        }
```

---

### 5.5 EnvService

```python
# app/services/env_service.py

import uuid
import re
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.env_variable import EnvVariable
from app.core.encryption import encrypt_value, decrypt_value


class EnvService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_env_vars(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
        var_type: Optional[str] = None,
    ) -> dict:
        """获取环境变量列表"""
        query = select(EnvVariable).where(EnvVariable.user_id == user_id)
        count_query = select(func.count(EnvVariable.id)).where(EnvVariable.user_id == user_id)

        if var_type:
            query = query.where(EnvVariable.type == var_type)
            count_query = count_query.where(EnvVariable.type == var_type)

        query = query.order_by(EnvVariable.key.asc())

        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        offset = (page - 1) * page_size
        result = await self.db.execute(query.offset(offset).limit(page_size))
        env_vars = result.scalars().all()

        items = []
        for ev in env_vars:
            item = {
                "id": ev.id,
                "key": ev.key,
                "type": ev.type.value if hasattr(ev.type, 'value') else ev.type,
                "created_at": ev.created_at,
                "updated_at": ev.updated_at,
            }
            if ev.type.value == "secret" if hasattr(ev.type, 'value') else ev.type == "secret":
                # 脱敏显示
                try:
                    decrypted = decrypt_value(ev.value_encrypted)
                    last4 = decrypted[-4:] if len(decrypted) >= 4 else "****"
                    item["masked_value"] = f"****{last4}"
                except Exception:
                    item["masked_value"] = "****"
            else:
                # string 类型返回明文
                try:
                    item["value"] = decrypt_value(ev.value_encrypted)
                except Exception:
                    item["value"] = ev.value_encrypted

            items.append(item)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": offset + page_size < total,
        }

    async def create_env_var(
        self,
        user_id: uuid.UUID,
        key: str,
        value: str,
        var_type: str = "string",
    ) -> EnvVariable:
        """创建环境变量"""
        # 校验 key 格式
        if not re.match(r"^[A-Z0-9_]+$", key):
            raise EnvVarKeyFormatError()

        # 检查唯一性
        existing = await self.db.execute(
            select(EnvVariable).where(
                EnvVariable.user_id == user_id,
                EnvVariable.key == key,
            )
        )
        if existing.scalar_one_or_none():
            raise EnvVarKeyExistsError()

        # 加密存储（统一使用 Fernet 加密所有值）
        encrypted = encrypt_value(value)

        env_var = EnvVariable(
            user_id=user_id,
            key=key,
            value_encrypted=encrypted,
            type=var_type,
        )
        self.db.add(env_var)
        await self.db.flush()
        return env_var

    async def update_env_var(
        self,
        env_var_id: uuid.UUID,
        user_id: uuid.UUID,
        value: Optional[str] = None,
        var_type: Optional[str] = None,
    ) -> EnvVariable:
        """更新环境变量"""
        result = await self.db.execute(
            select(EnvVariable).where(EnvVariable.id == env_var_id)
        )
        env_var = result.scalar_one_or_none()
        if not env_var:
            raise EnvVarNotFoundError()
        if env_var.user_id != user_id:
            raise ForbiddenError()

        # 不允许修改类型
        if var_type is not None:
            current_type = env_var.type.value if hasattr(env_var.type, 'value') else env_var.type
            if var_type != current_type:
                raise EnvVarTypeImmutableError()

        # 更新值
        if value is not None:
            env_var.value_encrypted = encrypt_value(value)

        await self.db.flush()
        return env_var

    async def delete_env_var(self, env_var_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """删除环境变量"""
        result = await self.db.execute(
            select(EnvVariable).where(EnvVariable.id == env_var_id)
        )
        env_var = result.scalar_one_or_none()
        if not env_var:
            raise EnvVarNotFoundError()
        if env_var.user_id != user_id:
            raise ForbiddenError()

        await self.db.delete(env_var)
        await self.db.flush()
```

---

## 6. 版本 Diff 算法

### 6.1 算法概述

版本 Diff 的核心目标：检测两个版本之间**节点和边的增删改**。

输入：`v1_nodes`, `v1_edges`, `v2_nodes`, `v2_edges`（JSONB 数组）

输出：
- `added_nodes`：v2 中有但 v1 中没有的节点
- `removed_nodes`：v1 中有但 v2 中没有的节点
- `modified_nodes`：v1 和 v2 中都有，但 `data` 内容不同的节点（含字段级 diff）
- `added_edges`：v2 中有但 v1 中没有的边
- `removed_edges`：v1 中有但 v2 中没有的边
- `modified_edges`：v1 和 v2 中都有，但内容不同的边

### 6.2 节点 Diff 算法

```python
def diff_nodes(v1_nodes: list, v2_nodes: list) -> dict:
    """
    对比两个版本的节点差异
    
    Returns:
        {
            "added": [...],       # 新增节点
            "removed": [...],     # 删除节点
            "modified": [...]     # 修改节点（含字段级变更）
        }
    """
    # 1. 建立 ID → 节点 的映射
    v1_map = {n["id"]: n for n in (v1_nodes or [])}
    v2_map = {n["id"]: n for n in (v2_nodes or [])}

    v1_ids = set(v1_map.keys())
    v2_ids = set(v2_map.keys())

    # 2. 新增节点：在 v2 中但不在 v1 中
    added_ids = v2_ids - v1_ids
    added = [
        {
            "id": nid,
            "type": v2_map[nid].get("type", "unknown"),
            "label": v2_map[nid].get("data", {}).get("label", ""),
            "position": v2_map[nid].get("position", {}),
        }
        for nid in added_ids
    ]

    # 3. 删除节点：在 v1 中但不在 v2 中
    removed_ids = v1_ids - v2_ids
    removed = [
        {
            "id": nid,
            "type": v1_map[nid].get("type", "unknown"),
            "label": v1_map[nid].get("data", {}).get("label", ""),
        }
        for nid in removed_ids
    ]

    # 4. 修改节点：两版本都有，但内容不同
    common_ids = v1_ids & v2_ids
    modified = []
    for nid in common_ids:
        n1 = v1_map[nid]
        n2 = v2_map[nid]
        changes = _deep_diff(n1.get("data", {}), n2.get("data", {}))
        if changes:
            modified.append({
                "id": nid,
                "type": n1.get("type", "unknown"),
                "label": n2.get("data", {}).get("label", n1.get("data", {}).get("label", "")),
                "changes": changes,
            })

    return {"added": added, "removed": removed, "modified": modified}
```

### 6.3 深度 Diff 辅助函数

```python
def _deep_diff(old: dict, new: dict, prefix: str = "") -> list:
    """
    递归对比两个字典的差异，返回变更列表
    
    Returns:
        [
            {"field": "data.agent_id", "old_value": "xxx", "new_value": "yyy"},
            {"field": "data.temperature", "old_value": 0.7, "new_value": 1.0},
        ]
    """
    changes = []
    all_keys = set(list(old.keys()) + list(new.keys()))

    for key in all_keys:
        field_path = f"{prefix}.{key}" if prefix else key
        old_val = old.get(key)
        new_val = new.get(key)

        if key not in old:
            # 新增字段
            changes.append({
                "field": field_path,
                "old_value": None,
                "new_value": new_val,
                "change_type": "added",
            })
        elif key not in new:
            # 删除字段
            changes.append({
                "field": field_path,
                "old_value": old_val,
                "new_value": None,
                "change_type": "removed",
            })
        elif isinstance(old_val, dict) and isinstance(new_val, dict):
            # 递归对比嵌套字典
            changes.extend(_deep_diff(old_val, new_val, field_path))
        elif isinstance(old_val, list) and isinstance(new_val, list):
            # 列表对比：简化为整体比较
            if old_val != new_val:
                changes.append({
                    "field": field_path,
                    "old_value": old_val,
                    "new_value": new_val,
                    "change_type": "modified",
                })
        elif old_val != new_val:
            # 基本类型值不同
            changes.append({
                "field": field_path,
                "old_value": old_val,
                "new_value": new_val,
                "change_type": "modified",
            })

    return changes
```

### 6.4 边 Diff 算法

```python
def diff_edges(v1_edges: list, v2_edges: list) -> dict:
    """
    对比两个版本的边差异
    
    边的唯一键：source + target + sourceHandle 组合
    """
    def edge_key(edge):
        return (
            edge.get("source", ""),
            edge.get("target", ""),
            edge.get("sourceHandle", ""),
        )

    v1_map = {edge_key(e): e for e in (v1_edges or [])}
    v2_map = {edge_key(e): e for e in (v2_edges or [])}

    v1_keys = set(v1_map.keys())
    v2_keys = set(v2_map.keys())

    added = [
        {
            "id": v2_map[k].get("id", ""),
            "source": k[0],
            "target": k[1],
            "source_handle": k[2],
        }
        for k in (v2_keys - v1_keys)
    ]

    removed = [
        {
            "id": v1_map[k].get("id", ""),
            "source": k[0],
            "target": k[1],
            "source_handle": k[2],
        }
        for k in (v1_keys - v2_keys)
    ]

    # 修改的边：相同 key 但其他属性不同
    modified = []
    for k in (v1_keys & v2_keys):
        e1 = v1_map[k]
        e2 = v2_map[k]
        if e1.get("type") != e2.get("type") or e1.get("data") != e2.get("data"):
            modified.append({
                "id": e1.get("id", ""),
                "source": k[0],
                "old_target": k[1],
                "new_target": k[1],
                "changes": _deep_diff(
                    {key: e1[key] for key in ["type", "data", "label"] if key in e1},
                    {key: e2[key] for key in ["type", "data", "label"] if key in e2},
                ),
            })

    return {"added": added, "removed": removed, "modified": modified}
```

### 6.5 完整 Diff 方法签名

```python
# 在 VersionService 中
async def diff_versions(
    self,
    workflow_id: uuid.UUID,
    v1: int,
    v2: int,
    user_id: uuid.UUID,
) -> dict:
    """对比两个版本的完整差异"""
    # 权限检查
    await self._get_workflow_with_auth(workflow_id, user_id)

    # 查询两个版本
    version1 = await self._get_version(workflow_id, v1)
    version2 = await self._get_version(workflow_id, v2)
    if not version1:
        raise VersionNotFoundError(v1)
    if not version2:
        raise VersionNotFoundError(v2)

    # 执行 Diff
    node_diff = diff_nodes(version1.nodes_data, version2.nodes_data)
    edge_diff = diff_edges(version1.edges_data, version2.edges_data)

    return {
        "v1": v1,
        "v2": v2,
        "added_nodes": node_diff["added"],
        "removed_nodes": node_diff["removed"],
        "modified_nodes": node_diff["modified"],
        "added_edges": edge_diff["added"],
        "removed_edges": edge_diff["removed"],
        "modified_edges": edge_diff["modified"],
    }
```

---

## 7. 环境变量加密方案

### 7.1 复用 Phase 2 的 Fernet 加密

Phase 2 已为 ModelProvider 的 `api_key_encrypted` 实现了 Fernet 加密。Phase 6 复用相同的加密模块。

```python
# app/core/encryption.py（Phase 2 已创建，Phase 6 确认可用）

from cryptography.fernet import Fernet
from app.core.config import settings


def _get_fernet() -> Fernet:
    """获取 Fernet 实例"""
    key = settings.fernet_key.encode()
    return Fernet(key)


def encrypt_value(plain_text: str) -> str:
    """加密明文值"""
    f = _get_fernet()
    return f.encrypt(plain_text.encode()).decode()


def decrypt_value(encrypted_text: str) -> str:
    """解密密文值"""
    f = _get_fernet()
    return f.decrypt(encrypted_text.encode()).decode()
```

### 7.2 加密策略

| 变量类型 | 存储方式 | 接口返回 | 说明 |
|---------|---------|---------|------|
| `string` | Fernet 加密后存储 | 返回明文 `value` | 非敏感数据，但统一加密保证安全 |
| `secret` | Fernet 加密后存储 | 返回 `masked_value`（`****xxxx`） | 敏感数据，永远脱敏 |

### 7.3 安全规则

1. **API 响应中永远不返回 `value_encrypted` 原始值**
2. **Secret 类型只返回 `masked_value`**，格式为 `****` + 原始值最后4位
3. **编辑 Secret 类型时必须重新输入完整值**，不支持部分更新
4. **不允许修改变量类型**（`string` ↔ `secret` 互转禁止）
5. **Fernet Key 泄露 = 所有加密值泄露**，需妥善保管 `.env` 中的 `FERNET_KEY`

### 7.4 依赖

```
# requirements.txt（Phase 2 已添加）
cryptography>=42.0.0
```

---

## 8. 错误码汇总

### 8.1 新增错误码

| HTTP 状态码 | 业务错误码 | 说明 | 适用模块 |
|------------|-----------|------|---------|
| **模板** | | | |
| 404 | `TEMPLATE_NOT_FOUND` | 模板不存在 | 模板 |
| 403 | `PRESET_TEMPLATE_PROTECTED` | 预置模板不可删除/修改 | 模板 |
| **版本标签** | | | |
| 400 | `NO_TAG_TO_REMOVE` | 该版本没有标签可删除 | 版本 |
| **执行历史** | | | |
| 404 | `EXECUTION_NOT_FOUND` | 执行记录不存在 | 执行 |
| **日志** | | | |
| 404 | `LOG_NOT_FOUND` | 日志不存在 | 日志 |
| **环境变量** | | | |
| 404 | `ENV_VAR_NOT_FOUND` | 环境变量不存在 | 环境变量 |
| 409 | `ENV_VAR_KEY_EXISTS` | 变量名已存在（同用户下唯一） | 环境变量 |
| 422 | `ENV_VAR_KEY_FORMAT` | 变量名格式不合法（只允许大写字母+数字+下划线） | 环境变量 |
| 400 | `ENV_VAR_TYPE_IMMUTABLE` | 不允许修改变量类型 | 环境变量 |

### 8.2 新增异常类

```python
# app/core/exceptions.py — Phase 6 新增

class TemplateNotFoundError(AppException):
    def __init__(self):
        super().__init__(code="TEMPLATE_NOT_FOUND", message="模板不存在", status_code=404)


class PresetTemplateProtectedError(AppException):
    def __init__(self):
        super().__init__(code="PRESET_TEMPLATE_PROTECTED", message="预置模板不可删除/修改", status_code=403)


class NoTagToRemoveError(AppException):
    def __init__(self):
        super().__init__(code="NO_TAG_TO_REMOVE", message="该版本没有标签可删除", status_code=400)


class ExecutionNotFoundError(AppException):
    def __init__(self):
        super().__init__(code="EXECUTION_NOT_FOUND", message="执行记录不存在", status_code=404)


class LogNotFoundError(AppException):
    def __init__(self):
        super().__init__(code="LOG_NOT_FOUND", message="日志不存在", status_code=404)


class EnvVarNotFoundError(AppException):
    def __init__(self):
        super().__init__(code="ENV_VAR_NOT_FOUND", message="环境变量不存在", status_code=404)


class EnvVarKeyExistsError(AppException):
    def __init__(self):
        super().__init__(code="ENV_VAR_KEY_EXISTS", message="变量名已存在", status_code=409)


class EnvVarKeyFormatError(AppException):
    def __init__(self):
        super().__init__(code="ENV_VAR_KEY_FORMAT", message="变量名格式不合法，只允许大写字母、数字和下划线", status_code=422)


class EnvVarTypeImmutableError(AppException):
    def __init__(self):
        super().__init__(code="ENV_VAR_TYPE_IMMUTABLE", message="不允许修改变量类型", status_code=400)
```

---

## 9. 与 Phase 0-5 的衔接

### 9.1 依赖关系总览

| 依赖 Phase | 模块 | 说明 |
|-----------|------|------|
| Phase 0 | 所有模型基础定义 | Template/Execution/ExecutionNode/Log/EnvVariable 的 ORM 模型 |
| Phase 0 | 中间件 | CORS、请求日志、全局异常处理 |
| Phase 0 | 数据库连接 | async engine + session factory |
| Phase 0 | Fernet 加密 | `app/core/encryption.py` |
| Phase 1 | 用户认证 | JWT + `get_current_user` 依赖注入 |
| Phase 2 | Fernet 加密实现 | `encrypt_value` / `decrypt_value` 工具函数 |
| Phase 4 | Workflow 模型 | `nodes_data` / `edges_data` 字段 |
| Phase 4 | WorkflowVersion 模型 | 版本管理基础 |
| Phase 4 | WorkflowService | `create_workflow` 方法（模板创建工作流时调用） |
| Phase 4 | VersionService | `diff_versions` 基础方法（Phase 6 增强） |
| Phase 5 | 执行引擎 | Execution/ExecutionNode/Log 记录的写入（Phase 6 读取查询） |

### 9.2 目录结构变更

```
app/
├── models/
│   ├── template.py             # 【修改】新增 user_id, nodes_data, edges_data, is_preset 字段
│   ├── env_variable.py         # 【修改】新增 (user_id, key) 复合唯一约束
│   └── execution.py            # 【不变】Phase 0 定义，Phase 5 使用，Phase 6 查询
├── schemas/
│   ├── template.py             # 【重写】Phase 6 完整 Schema
│   ├── execution.py            # 【重写】Phase 6 完整 Schema（含统计）
│   ├── env_variable.py         # 【重写】Phase 6 完整 Schema
│   └── log.py                  # 【新增】日志相关 Schema
├── services/
│   ├── template_service.py     # 【新增】模板 CRUD + 使用
│   ├── version_service.py      # 【修改】Phase 4 基础上增强（打标签/删标签）
│   ├── execution_service.py    # 【新增】执行历史查询 + 统计
│   ├── log_service.py          # 【新增】日志查询
│   └── env_service.py          # 【新增】环境变量 CRUD
├── core/
│   ├── encryption.py           # 【确认】Phase 2 已实现，复用
│   └── exceptions.py           # 【修改】新增 Phase 6 异常类
├── api/
│   └── v1/
│       ├── templates.py        # 【重写】从空骨架到完整实现
│       ├── executions.py       # 【重写】从空骨架到完整实现
│       ├── env_vars.py         # 【重写】从空骨架到完整实现
│       └── logs.py             # 【新增】日志路由
├── seeds/
│   └── preset_templates.py     # 【新增】预置模板种子数据
└── tests/
    ├── test_templates.py       # 【新增】
    ├── test_execution_history.py # 【新增】
    ├── test_logs.py            # 【新增】
    ├── test_env_vars.py        # 【新增】
    └── test_version_tag.py     # 【新增】
```

### 9.3 路由注册

确保以下路由在 `app/api/router.py` 中正确挂载：

```python
from app.api.v1 import templates, executions, env_vars, logs, workflows

api_router = APIRouter(prefix="/api")

# 模板路由
api_router.include_router(templates.router, prefix="/templates", tags=["Templates"])

# 执行历史路由
api_router.include_router(executions.router, prefix="/executions", tags=["Executions"])

# 环境变量路由
api_router.include_router(env_vars.router, prefix="/env-vars", tags=["Env Variables"])

# 日志路由
api_router.include_router(logs.router, prefix="/logs", tags=["Logs"])

# 工作流路由中的新增端点
# POST /api/workflows/:id/save-as-template  → 在 workflows.py 中添加
```

### 9.4 依赖安装

```
# requirements.txt — Phase 6 无新增依赖
# Phase 0-5 已包含所有需要的库：
# - sqlalchemy, asyncpg, pydantic, cryptography 等
# 如需全文搜索增强，可选添加：
# psycopg2-binary>=2.9.9  # 如果使用 pg_trgm
```

---

## 10. 测试用例

### 10.1 模板系统测试

| 编号 | 前置条件 | 步骤 | 预期结果 | 优先级 |
|------|---------|------|---------|--------|
| TPL-001 | 系统已初始化 | GET /api/templates | 返回 4 个预置模板 | P0 |
| TPL-002 | 存在预置模板 | GET /api/templates/:id | 返回完整详情含 nodes_data | P0 |
| TPL-003 | 存在工作流 | POST /workflows/:id/save-as-template | 创建自定义模板，is_preset=false | P0 |
| TPL-004 | 存在自定义模板 | POST /api/templates/:id/use | 创建新工作流，use_count+1 | P0 |
| TPL-005 | 存在自定义模板 | DELETE /api/templates/:id | 删除成功 | P0 |
| TPL-006 | 存在预置模板 | DELETE /api/templates/:id | 403 PRESET_TEMPLATE_PROTECTED | P0 |
| TPL-007 | 存在预置模板 | PUT 修改预置模板 | 403 PRESET_TEMPLATE_PROTECTED | P0 |
| TPL-008 | 4 个预置模板 | GET /api/templates?category=软件开发 | 只返回 1 个模板 | P1 |
| TPL-009 | 存在模板 | GET /api/templates?keyword=全流程 | 返回包含"全流程"的模板 | P1 |
| TPL-010 | 用户 A 创建模板 | 用户 B DELETE 该模板 | 403 FORBIDDEN | P1 |

### 10.2 版本标签测试

| 编号 | 前置条件 | 步骤 | 预期结果 | 优先级 |
|------|---------|------|---------|--------|
| TAG-001 | 存在工作流和版本 v1 | POST /workflows/:id/versions/1/tag | tag 设置为指定值 | P0 |
| TAG-002 | 版本 v1 有标签 | DELETE /workflows/:id/versions/1/tag | tag 变为 null | P0 |
| TAG-003 | 版本 v1 无标签 | DELETE /workflows/:id/versions/1/tag | 400 NO_TAG_TO_REMOVE | P1 |
| TAG-004 | 不存在版本 v999 | POST /workflows/:id/versions/999/tag | 404 VERSION_NOT_FOUND | P1 |

### 10.3 执行历史测试

| 编号 | 前置条件 | 步骤 | 预期结果 | 优先级 |
|------|---------|------|---------|--------|
| EXEC-001 | 有执行记录 | GET /api/executions | 返回列表，含工作流名称 | P0 |
| EXEC-002 | 有多次执行 | GET /api/executions?status=success | 只返回成功记录 | P0 |
| EXEC-003 | 有执行记录 | GET /api/executions/:id | 返回详情含所有节点 | P0 |
| EXEC-004 | 有执行记录 | GET /api/executions/stats | 返回统计数据 | P0 |
| EXEC-005 | 有执行记录 | GET /api/executions?workflow_id=xxx | 按工作流筛选 | P1 |
| EXEC-006 | 有执行记录 | GET /api/executions?start_time=...&end_time=... | 按时间筛选 | P1 |
| EXEC-007 | 用户 A 的执行 | 用户 B GET /api/executions/:id | 403 FORBIDDEN | P1 |
| EXEC-008 | 有执行记录 | GET /api/executions/stats?period=30d | 返回 30 天统计 | P1 |

### 10.4 日志中心测试

| 编号 | 前置条件 | 步骤 | 预期结果 | 优先级 |
|------|---------|------|---------|--------|
| LOG-001 | 有日志记录 | GET /api/logs | 返回列表 | P0 |
| LOG-002 | 有日志记录 | GET /api/logs/:id | 返回详情 | P0 |
| LOG-003 | 有日志记录 | GET /api/logs?level=error | 只返回 error 级别 | P1 |
| LOG-004 | 有日志记录 | GET /api/logs?execution_id=xxx | 按执行筛选 | P1 |
| LOG-005 | 有日志记录 | GET /api/logs?search=失败 | 全文搜索 message | P1 |
| LOG-006 | 不存在日志 | GET /api/logs/:id | 404 LOG_NOT_FOUND | P1 |

### 10.5 环境变量测试

| 编号 | 前置条件 | 步骤 | 预期结果 | 优先级 |
|------|---------|------|---------|--------|
| ENV-001 | 用户已登录 | POST /api/env-vars（string 类型） | 创建成功，返回明文 value | P0 |
| ENV-002 | 用户已登录 | POST /api/env-vars（secret 类型） | 创建成功，返回 masked_value | P0 |
| ENV-003 | 存在变量 | GET /api/env-vars | 列表展示，secret 脱敏 | P0 |
| ENV-004 | 存在变量 | PUT /api/env-vars/:id | 更新值成功 | P0 |
| ENV-005 | 存在变量 | DELETE /api/env-vars/:id | 删除成功 | P0 |
| ENV-006 | - | POST key="abc"（小写） | 422 ENV_VAR_KEY_FORMAT | P0 |
| ENV-007 | 已存在 OPENAI_API_KEY | POST key="OPENAI_API_KEY" | 409 ENV_VAR_KEY_EXISTS | P0 |
| ENV-008 | 存在 string 类型 | PUT type="secret" | 400 ENV_VAR_TYPE_IMMUTABLE | P1 |
| ENV-009 | 存在 secret 变量 | GET /api/env-vars | value 字段不出现，只有 masked_value | P0 |
| ENV-010 | - | POST key="VALID_KEY_123" | 创建成功 | P1 |

---

## 11. Pydantic Schema 完整定义

### 11.1 `app/schemas/template.py`

```python
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


class SaveAsTemplateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    category: str = Field(default="自定义", max_length=100)
    thumbnail_url: Optional[str] = None


class UseTemplateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)


class TemplateListItem(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    category: str
    thumbnail_url: Optional[str] = None
    use_count: int
    node_count: int = 0
    is_preset: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TemplateListResponse(BaseModel):
    items: list[TemplateListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class TemplateDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    category: str
    thumbnail_url: Optional[str] = None
    use_count: int
    is_preset: bool
    nodes_data: Optional[list] = None
    edges_data: Optional[list] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TemplateDeleteResponse(BaseModel):
    message: str = "模板已删除"
    template_id: uuid.UUID
```

### 11.2 `app/schemas/execution.py`（Phase 6 重写）

```python
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ExecutionListItem(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: str
    version_number: int
    status: str
    total_duration_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    total_cost: Optional[float] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    node_count: int = 0
    success_node_count: int = 0
    failed_node_count: int = 0

    model_config = {"from_attributes": True}


class ExecutionListResponse(BaseModel):
    items: list[ExecutionListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class ExecutionNodeDetail(BaseModel):
    id: uuid.UUID
    node_id: str
    node_type: str
    status: str
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    duration_ms: Optional[int] = None
    tokens_used: Optional[int] = None
    error_message: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class NodeStats(BaseModel):
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    pending: int = 0
    running: int = 0
    paused: int = 0


class ExecutionDetailResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: str
    version_number: int
    status: str
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    total_duration_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    total_cost: Optional[float] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    nodes: list[ExecutionNodeDetail] = []
    node_stats: NodeStats = NodeStats()
    success_rate: float = 0.0
    log_count: int = 0


class ExecutionStatsSummary(BaseModel):
    total_executions: int
    success_count: int
    failed_count: int
    success_rate: float
    avg_duration_ms: int
    total_tokens: int
    total_cost: float


class DailyTrendItem(BaseModel):
    date: str
    count: int
    success_count: int
    avg_duration_ms: int


class WorkflowStatsItem(BaseModel):
    workflow_id: str
    workflow_name: str
    execution_count: int
    success_count: int
    avg_duration_ms: int


class ExecutionStatsResponse(BaseModel):
    summary: ExecutionStatsSummary
    daily_trend: list[DailyTrendItem]
    by_workflow: list[WorkflowStatsItem]
```

### 11.3 `app/schemas/log.py`

```python
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class LogListItem(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    workflow_name: str
    level: str
    message: str
    node_id: Optional[str] = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class LogListResponse(BaseModel):
    items: list[LogListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class LogDetailResponse(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: str
    level: str
    message: str
    node_id: Optional[str] = None
    timestamp: datetime
    metadata: dict = {}

    model_config = {"from_attributes": True}
```

### 11.4 `app/schemas/env_variable.py`（Phase 6 重写）

```python
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class EnvVarCreateRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=255, pattern=r"^[A-Z0-9_]+$")
    value: str = Field(..., min_length=1, max_length=10000)
    type: str = Field(default="string", pattern="^(string|secret)$")


class EnvVarUpdateRequest(BaseModel):
    value: Optional[str] = Field(default=None, min_length=1, max_length=10000)
    type: Optional[str] = Field(default=None, pattern="^(string|secret)$")


class EnvVarListItem(BaseModel):
    id: uuid.UUID
    key: str
    type: str
    value: Optional[str] = None         # string 类型有值
    masked_value: Optional[str] = None  # secret 类型有值
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EnvVarListResponse(BaseModel):
    items: list[EnvVarListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class EnvVarResponse(BaseModel):
    id: uuid.UUID
    key: str
    type: str
    value: Optional[str] = None
    masked_value: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EnvVarDeleteResponse(BaseModel):
    message: str = "环境变量已删除"
    env_var_id: uuid.UUID
```

### 11.5 `app/schemas/version.py`（Phase 6 新增标签相关）

```python
# 追加到 Phase 4 已有的 schema 文件中

from pydantic import BaseModel, Field


class TagVersionRequest(BaseModel):
    tag: str = Field(..., min_length=1, max_length=100)


class VersionTagResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    version_number: int
    tag: Optional[str] = None
    node_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}
```

---

## 12. API 路由实现

### 12.1 `app/api/v1/templates.py`

```python
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DBSession
from app.services.template_service import TemplateService
from app.schemas.template import (
    SaveAsTemplateRequest, UseTemplateRequest,
    TemplateListResponse, TemplateDetailResponse, TemplateDeleteResponse,
)

router = APIRouter()


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, max_length=100),
    category: Optional[str] = Query(None),
    is_preset: Optional[bool] = Query(None),
    sort_by: str = Query("use_count", pattern="^(name|created_at|use_count)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
):
    """获取模板列表"""
    service = TemplateService(db)
    result = await service.list_templates(
        page=page, page_size=page_size, keyword=keyword,
        category=category, is_preset=is_preset,
        sort_by=sort_by, sort_order=sort_order,
    )
    return {"code": 0, "message": "success", "data": result}


@router.get("/{template_id}", response_model=TemplateDetailResponse)
async def get_template(template_id: UUID, db: DBSession):
    """获取模板详情"""
    service = TemplateService(db)
    template = await service.get_template(template_id)
    return {
        "code": 0, "message": "success",
        "data": {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "category": template.category,
            "thumbnail_url": template.thumbnail_url,
            "use_count": template.use_count,
            "is_preset": template.is_preset,
            "nodes_data": template.nodes_data,
            "edges_data": template.edges_data,
            "created_at": template.created_at,
        }
    }


@router.post("/{template_id}/use")
async def use_template(
    template_id: UUID,
    body: UseTemplateRequest,
    db: DBSession,
    user: CurrentUser,
):
    """使用模板创建工作流"""
    service = TemplateService(db)
    workflow = await service.use_template(template_id, user.id, body.name)
    return {"code": 0, "message": "success", "data": workflow}


@router.delete("/{template_id}", response_model=TemplateDeleteResponse)
async def delete_template(template_id: UUID, db: DBSession, user: CurrentUser):
    """删除自定义模板"""
    service = TemplateService(db)
    await service.delete_template(template_id, user.id)
    return {
        "code": 0, "message": "success",
        "data": {"message": "模板已删除", "template_id": template_id}
    }
```

### 12.2 工作流路由中新增端点

在 `app/api/v1/workflows.py` 中追加：

```python
# 追加到 workflows.py

@router.post("/{workflow_id}/save-as-template")
async def save_as_template(
    workflow_id: UUID,
    body: SaveAsTemplateRequest,
    db: DBSession,
    user: CurrentUser,
):
    """工作流保存为模板"""
    service = TemplateService(db)
    template = await service.save_as_template(
        workflow_id=workflow_id,
        user_id=user.id,
        name=body.name,
        description=body.description,
        category=body.category,
        thumbnail_url=body.thumbnail_url,
    )
    return {"code": 0, "message": "success", "data": template}


# 版本标签端点
@router.post("/{workflow_id}/versions/{version_number}/tag")
async def tag_version(
    workflow_id: UUID,
    version_number: int,
    body: TagVersionRequest,
    db: DBSession,
    user: CurrentUser,
):
    """为版本打标签"""
    from app.services.version_service import VersionService
    service = VersionService(db)
    result = await service.tag_version(workflow_id, version_number, body.tag, user.id)
    return {"code": 0, "message": "success", "data": result}


@router.delete("/{workflow_id}/versions/{version_number}/tag")
async def remove_tag(
    workflow_id: UUID,
    version_number: int,
    db: DBSession,
    user: CurrentUser,
):
    """删除版本标签"""
    from app.services.version_service import VersionService
    service = VersionService(db)
    result = await service.remove_tag(workflow_id, version_number, user.id)
    return {"code": 0, "message": "success", "data": result}
```

### 12.3 `app/api/v1/executions.py`

```python
from uuid import UUID
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DBSession
from app.services.execution_service import ExecutionService

router = APIRouter()


@router.get("")
async def list_executions(
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    workflow_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None, pattern="^(pending|running|success|failed|paused|cancelled)$"),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
):
    """获取执行历史列表"""
    service = ExecutionService(db)
    result = await service.list_executions(
        user_id=user.id, page=page, page_size=page_size,
        workflow_id=workflow_id, status=status,
        start_time=start_time, end_time=end_time,
    )
    return {"code": 0, "message": "success", "data": result}


@router.get("/stats")
async def get_execution_stats(
    db: DBSession,
    user: CurrentUser,
    workflow_id: Optional[UUID] = Query(None),
    period: str = Query("7d", pattern="^(7d|30d|90d)$"),
):
    """获取执行统计"""
    service = ExecutionService(db)
    result = await service.get_stats(user.id, period=period, workflow_id=workflow_id)
    return {"code": 0, "message": "success", "data": result}


@router.get("/{execution_id}")
async def get_execution(execution_id: UUID, db: DBSession, user: CurrentUser):
    """获取执行详情"""
    service = ExecutionService(db)
    result = await service.get_execution(execution_id, user.id)
    return {"code": 0, "message": "success", "data": result}
```

### 12.4 `app/api/v1/logs.py`

```python
from uuid import UUID
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.services.log_service import LogService

router = APIRouter()


@router.get("")
async def list_logs(
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    level: Optional[str] = Query(None, pattern="^(info|warn|error)$"),
    execution_id: Optional[UUID] = Query(None),
    node_id: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    search: Optional[str] = Query(None, max_length=200),
):
    """获取日志列表"""
    service = LogService(db)
    result = await service.list_logs(
        user_id=user.id, page=page, page_size=page_size,
        level=level, execution_id=execution_id, node_id=node_id,
        start_time=start_time, end_time=end_time, search=search,
    )
    return {"code": 0, "message": "success", "data": result}


@router.get("/{log_id}")
async def get_log(log_id: UUID, db: DBSession, user: CurrentUser):
    """获取日志详情"""
    service = LogService(db)
    result = await service.get_log(log_id, user.id)
    return {"code": 0, "message": "success", "data": result}
```

### 12.5 `app/api/v1/env_vars.py`

```python
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.services.env_service import EnvService
from app.schemas.env_variable import (
    EnvVarCreateRequest, EnvVarUpdateRequest,
    EnvVarListResponse, EnvVarResponse, EnvVarDeleteResponse,
)

router = APIRouter()


@router.get("", response_model=EnvVarListResponse)
async def list_env_vars(
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    type: Optional[str] = Query(None, pattern="^(string|secret)$"),
):
    """获取环境变量列表"""
    service = EnvService(db)
    result = await service.list_env_vars(user.id, page=page, page_size=page_size, var_type=type)
    return {"code": 0, "message": "success", "data": result}


@router.post("", response_model=EnvVarResponse)
async def create_env_var(body: EnvVarCreateRequest, db: DBSession, user: CurrentUser):
    """创建环境变量"""
    service = EnvService(db)
    env_var = await service.create_env_var(user.id, body.key, body.value, body.type)
    # 构造响应（脱敏）
    return {"code": 0, "message": "success", "data": _format_env_var(env_var)}


@router.put("/{env_var_id}", response_model=EnvVarResponse)
async def update_env_var(
    env_var_id: UUID,
    body: EnvVarUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    """更新环境变量"""
    service = EnvService(db)
    env_var = await service.update_env_var(env_var_id, user.id, body.value, body.type)
    return {"code": 0, "message": "success", "data": _format_env_var(env_var)}


@router.delete("/{env_var_id}", response_model=EnvVarDeleteResponse)
async def delete_env_var(env_var_id: UUID, db: DBSession, user: CurrentUser):
    """删除环境变量"""
    service = EnvService(db)
    await service.delete_env_var(env_var_id, user.id)
    return {
        "code": 0, "message": "success",
        "data": {"message": "环境变量已删除", "env_var_id": env_var_id}
    }


def _format_env_var(env_var) -> dict:
    """格式化环境变量响应（脱敏处理）"""
    from app.core.encryption import decrypt_value
    
    item = {
        "id": env_var.id,
        "key": env_var.key,
        "type": env_var.type.value if hasattr(env_var.type, 'value') else env_var.type,
        "created_at": env_var.created_at,
        "updated_at": env_var.updated_at,
    }
    
    var_type = item["type"]
    if var_type == "secret":
        try:
            decrypted = decrypt_value(env_var.value_encrypted)
            last4 = decrypted[-4:] if len(decrypted) >= 4 else "****"
            item["masked_value"] = f"****{last4}"
        except Exception:
            item["masked_value"] = "****"
    else:
        try:
            item["value"] = decrypt_value(env_var.value_encrypted)
        except Exception:
            item["value"] = ""
    
    return item
```

---

## 13. 给 Cursor 的额外说明

### 13.1 实现顺序建议

Cursor 应按以下顺序实现，每完成一步确保测试通过后再进行下一步：

1. **数据库迁移**：
   - Template 模型字段变更（新增 user_id, nodes_data, edges_data, is_preset）
   - EnvVariable 新增复合唯一约束
   - Logs 新增 pg_trgm 索引
   - Executions 新增统计索引
   - 插入 4 个预置模板种子数据

2. **Schema 定义**：
   - `app/schemas/template.py`
   - `app/schemas/execution.py`（重写）
   - `app/schemas/log.py`（新增）
   - `app/schemas/env_variable.py`（重写）
   - `app/schemas/version.py`（追加标签相关）

3. **异常类**：`app/core/exceptions.py` 新增 Phase 6 异常

4. **加密模块确认**：确认 `app/core/encryption.py` 存在且可用

5. **Service 层**：
   - `TemplateService` → 单元测试
   - `VersionService` 增强（tag_version, remove_tag）→ 单元测试
   - `ExecutionService` → 单元测试
   - `LogService` → 单元测试
   - `EnvService` → 单元测试

6. **API 路由**：
   - `templates.py` → 集成测试
   - `workflows.py` 追加 save-as-template + tag 端点
   - `executions.py` → 集成测试
   - `logs.py` → 集成测试
   - `env_vars.py` → 集成测试

7. **Diff 算法**：实现 `diff_nodes` / `diff_edges` / `_deep_diff` → 单元测试

### 13.2 关键注意事项

1. **Template 模型的 workflow_id 改为 nullable**：Phase 0 中 workflow_id 是 NOT NULL + UNIQUE。Phase 6 改为 nullable 并去掉 UNIQUE。Alembic 迁移中需要：
   ```python
   op.alter_column("templates", "workflow_id", existing_type=..., nullable=True)
   op.drop_constraint("templates_workflow_id_key", "templates", type_="unique")
   ```

2. **预置模板的 user_id 为 NULL**：表示系统级别模板，不归属于任何用户。使用模板时不检查 user_id 权限。

3. **使用模板创建工作流是深拷贝**：必须使用 `copy.deepcopy()` 复制 `nodes_data` 和 `edges_data`，避免后续修改影响模板数据。

4. **执行统计的 SQL 查询**：使用 `func.count().filter()` 实现条件计数（PostgreSQL 特有语法）。如数据库不支持，改为 `CASE WHEN` 写法。

5. **日志全文搜索**：使用 `ILIKE` + `pg_trgm` GIN 索引加速。对于大数据量场景（>100 万条），后续可升级为 PostgreSQL `tsvector` 全文搜索。

6. **环境变量的加密统一**：所有变量（包括 string 类型）都使用 Fernet 加密存储，保持一致性。区别仅在于 API 响应时：string 返回明文，secret 返回脱敏值。

7. **版本 Diff 的节点匹配**：使用节点 `id` 字段（React Flow 前端生成的唯一 ID）作为匹配键。

8. **版本标签是覆盖式的**：每次 `POST tag` 直接覆盖旧标签，不支持多标签。

9. **执行记录的权限模型**：通过 `execution → workflow → user_id` 链路验证权限。用户只能查看自己工作流的执行记录。

10. **预置模板分类**：种子数据使用中文分类名（"软件开发"、"代码质量"等）。后端不对 `category` 做枚举限制，前端可以任意输入分类值。

### 13.3 代码风格约定

- 所有 Service 方法使用 `async/await`
- 日志使用 `structlog`，格式：`logger.info("event_name", key=value)`
- 所有数据库操作使用 `await self.db.flush()` 而非 `commit()`
- Pydantic Schema 使用 `model_config = {"from_attributes": True}`
- 异常类继承自 `AppException`
- UUID 参数在路由层使用 `UUID` 类型
- API 响应统一包裹为 `{"code": 0, "message": "success", "data": {...}}`

### 13.4 测试框架

复用 Phase 4 的测试 fixtures，确保以下 fixture 可用：

```python
# tests/conftest.py — Phase 6 需要的额外 fixtures

import pytest
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import Template
from app.models.execution import Execution, ExecutionNode, Log
from app.models.env_variable import EnvVariable


@pytest.fixture
async def sample_execution(db_session: AsyncSession, sample_workflow):
    """创建测试执行记录"""
    execution = Execution(
        workflow_id=sample_workflow.id,
        version_number=1,
        status="success",
        input_data={"query": "test"},
        output_data={"result": "test result"},
        total_duration_ms=5000,
        total_tokens=100,
    )
    db_session.add(execution)
    await db_session.flush()
    return execution


@pytest.fixture
async def sample_execution_node(db_session: AsyncSession, sample_execution):
    """创建测试节点执行记录"""
    node = ExecutionNode(
        execution_id=sample_execution.id,
        node_id="node_start_1",
        node_type="startNode",
        status="success",
        input_data={"query": "test"},
        output_data={"query": "test"},
        duration_ms=10,
        tokens_used=0,
    )
    db_session.add(node)
    await db_session.flush()
    return node


@pytest.fixture
async def sample_log(db_session: AsyncSession, sample_execution):
    """创建测试日志"""
    log = Log(
        execution_id=sample_execution.id,
        level="info",
        message="开始执行工作流",
        node_id="node_start_1",
    )
    db_session.add(log)
    await db_session.flush()
    return log


@pytest.fixture
async def preset_templates(db_session: AsyncSession):
    """确保预置模板存在"""
    # 从种子数据插入或使用已有的
    pass
```

### 13.5 验证清单（Phase 6 完成标准）

- [ ] `GET /api/templates` 返回 4 个预置模板
- [ ] `POST /api/workflows/:id/save-as-template` 创建自定义模板
- [ ] `POST /api/templates/:id/use` 基于模板创建工作流
- [ ] `DELETE /api/templates/:id` 只能删除自定义模板，预置模板返回 403
- [ ] `POST /api/workflows/:id/versions/:ver/tag` 成功打标签
- [ ] `DELETE /api/workflows/:id/versions/:ver/tag` 成功删标签
- [ ] `GET /api/workflows/:id/versions/diff` 返回正确的节点增删改差异
- [ ] `GET /api/executions` 支持分页、按工作流/状态/时间筛选
- [ ] `GET /api/executions/:id` 返回完整节点执行记录和统计
- [ ] `GET /api/executions/stats` 返回正确的聚合统计
- [ ] `GET /api/logs` 支持分页、筛选和全文搜索
- [ ] `GET /api/env-vars` 列表正确脱敏
- [ ] `POST /api/env-vars` 创建成功，key 格式校验生效
- [ ] `PUT /api/env-vars/:id` 更新值，禁止改类型
- [ ] `DELETE /api/env-vars/:id` 删除成功
- [ ] Secret 类型加密存储，API 永远不返回明文
- [ ] 变量名唯一性约束生效（同用户下）
- [ ] 所有接口权限校验正确

---

**文档结束**。Phase 6 后端开发完成后，平台将具备完整的模板管理、版本标签、执行历史、日志中心和环境变量管理能力，为 Phase 7（Dashboard + API 发布 + 打磨）做好数据基础。

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
