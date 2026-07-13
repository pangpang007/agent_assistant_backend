---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 4263223131904378_0/project_7661866342080954651-files/Phase2/phase2_backend.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 4263223131904378#1783934534282
    ReservedCode2: ""
---
# 汤圆的代码助手 - Phase 2 后端开发文档：Agent 管理 + 工具系统 + 模型管理

> **目标读者**：Cursor / AI Coding Agent  
> **版本**：Phase 2 v1.0  
> **项目代号**：`tangyuan-backend`  
> **前置条件**：Phase 0（脚手架 + 全部数据库模型）+ Phase 1（用户系统）已完成

---

## 1. 目标

在 Phase 1 基础上实现 Agent 管理、工具系统、模型管理三大模块：

- **Agent CRUD**：预置 Agent（系统 seed，不可删除/修改，可复制为自定义）+ 自定义 Agent 完整 CRUD
- **工具系统**：预置工具（系统 seed，7 个内置工具）+ 自定义工具（OpenAPI/Swagger 导入）+ 工具测试
- **模型管理**：供应商 CRUD + API Key 加密存储 + 模型配置 + 用量统计
- **关联表**：Agent-Tool 多对多关联、Agent-KnowledgeBase 多对多关联（Phase 3 激活，Phase 2 先建表）

Phase 2 完成后，用户应能完成：添加模型供应商→配置模型→创建/管理 Agent→创建/管理工具→将工具挂载到 Agent 的完整流程。

---

## 2. 数据库变更

### 2.1 现有模型修改

#### 2.1.1 Agent 模型重构 `app/models/agent.py`

Phase 0 的 Agent 模型使用 `model_provider`（字符串）和 `tools`（JSONB 数组）存储模型和工具关系。Phase 2 需要将其重构为外键关系，以支持关联表和真正的模型选择。

```python
# app/models/agent.py — Phase 2 重构后的完整模型

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, Boolean, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin
from .enums import MemoryStrategy, OutputFormat


class Agent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agents"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Phase 2 重构：model_id 外键指向 llm_models 表
    model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_models.id", ondelete="SET NULL"), nullable=True, index=True
    )

    memory_strategy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="none", server_default="none"
    )
    output_format: Mapped[str] = mapped_column(
        String(20), nullable=False, default="markdown", server_default="markdown"
    )
    temperature: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.7, server_default="0.7"
    )
    max_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=4096, server_default="4096"
    )
    is_preset: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Relationships
    user = relationship("User", back_populates="agents")
    model = relationship("LLMModel", back_populates="agents")
    agent_tools = relationship("AgentTool", back_populates="agent", cascade="all, delete-orphan")
    agent_knowledge_bases = relationship(
        "AgentKnowledgeBase", back_populates="agent", cascade="all, delete-orphan"
    )
```

**变更说明**：

| 变更项 | Phase 0 | Phase 2 |
|--------|---------|---------|
| 模型选择 | `model_provider` (String) + `model_name` (String) | `model_id` (UUID FK → llm_models.id) |
| 工具关联 | `tools` (JSONB 数组) | 通过 `agent_tool` 关联表 |
| 知识库关联 | `knowledge_base_ids` (JSONB 数组) | 通过 `agent_knowledge_base` 关联表 |

**迁移策略**：
- 删除 `model_provider`、`model_name`、`tools`、`knowledge_base_ids` 四个列
- 新增 `model_id` 外键列
- 预置 Agent 数据重新 seed，不受迁移影响

#### 2.1.2 Tool 模型重构 `app/models/tool.py`

Phase 0 的 Tool 模型过于简单（`type` 枚举 + `config` JSONB）。Phase 2 需要明确拆分字段以支持 OpenAPI 导入和工具测试。

```python
# app/models/tool.py — Phase 2 重构后的完整模型

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class Tool(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tools"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Phase 2 重构：明确字段
    tool_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="custom", server_default="custom"
    )
    # tool_type 取值: "preset" | "custom"

    # 自定义工具的 API 配置
    openapi_spec: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # openapi_spec: 完整的 OpenAPI 3.0 规范 JSON（自定义工具导入时解析）

    api_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    # api_url: 工具的调用端点 URL

    auth_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="none", server_default="none"
    )
    # auth_type 取值: "none" | "api_key" | "bearer"

    auth_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # auth_config 结构:
    # auth_type=api_key: {"header_name": "X-API-Key", "api_key_value_encrypted": "..."}
    # auth_type=bearer: {"token_encrypted": "..."}

    is_preset: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Relationships
    user = relationship("User", back_populates="tools")
    agent_tools = relationship("AgentTool", back_populates="tool", cascade="all, delete-orphan")
```

**变更说明**：

| 变更项 | Phase 0 | Phase 2 |
|--------|---------|---------|
| 类型字段 | `type` (ToolType 枚举) | `tool_type` (String: "preset" / "custom") |
| 配置 | `config` (JSONB) | 拆分为 `openapi_spec`、`api_url`、`auth_type`、`auth_config` |

**迁移策略**：
- 删除 `type`、`config` 列
- 新增 `tool_type`、`openapi_spec`、`api_url`、`auth_type`、`auth_config` 列

#### 2.1.3 ModelProvider 模型扩展 `app/models/model_provider.py`

Phase 0 的 ModelProvider 没有 `provider_type` 字段，也没有模型列表管理。Phase 2 需要新增 `provider_type` 和独立的 `LLMModel` 表。

```python
# app/models/model_provider.py — Phase 2 重构后的完整模型

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Boolean, Integer, Date, Numeric, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class ModelProvider(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "model_providers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Phase 2 新增
    provider_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="custom", server_default="custom"
    )
    # provider_type 取值: "openai" | "anthropic" | "google" | "custom"
    # - openai: OpenAI 官方 API
    # - anthropic: Anthropic Claude API
    # - google: Google Gemini API
    # - custom: 自定义 OpenAI 兼容接口（如 Ollama、vLLM、第三方中转等）

    api_key_encrypted: Mapped[str] = mapped_column(String(1024), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    # base_url: custom 类型必填（如 http://localhost:11434/v1）
    #           openai/anthropic/google 可选覆盖（用于代理）

    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Relationships
    user = relationship("User", back_populates="model_providers")
    models = relationship("LLMModel", back_populates="provider", cascade="all, delete-orphan")


class LLMModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """模型提供商下的具体模型配置"""
    __tablename__ = "llm_models"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 如 gpt-4o, claude-3-5-sonnet-20241022, gemini-1.5-pro 等

    display_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # 展示名称，如 "GPT-4o"、"Claude 3.5 Sonnet"

    input_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=0, server_default="0"
    )
    # 每百万 token 输入价格（USD）

    output_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=0, server_default="0"
    )
    # 每百万 token 输出价格（USD）

    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # 同一用户下仅允许一个模型为默认（业务层保证）

    # Relationships
    provider = relationship("ModelProvider", back_populates="models")
    agents = relationship("Agent", back_populates="model")


class ModelUsage(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "model_usages"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_providers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_models.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        __import__("sqlalchemy").DateTime(timezone=True),
        server_default=__import__("sqlalchemy").func.now(),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="model_usages")
```

**变更说明**：

| 变更项 | Phase 0 | Phase 2 |
|--------|---------|---------|
| 供应商类型 | 无 | 新增 `provider_type` |
| 启用/禁用 | `enabled` | 改名为 `is_enabled`（统一命名规范） |
| 模型列表 | 无独立表 | 新增 `llm_models` 表 |
| 用量表 | `provider_name` + `model_name`（字符串） | 新增 `provider_id` + `model_id` 外键，保留字符串冗余字段便于历史查询 |

### 2.2 新增关联表

#### 2.2.1 `agent_tool` 关联表

```python
# app/models/agent_tool.py — Phase 2 新增文件

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, DateTime, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin


class AgentTool(Base, UUIDPrimaryKeyMixin):
    """Agent-Tool 多对多关联表"""
    __tablename__ = "agent_tools"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    agent = relationship("Agent", back_populates="agent_tools")
    tool = relationship("Tool", back_populates="agent_tools")

    # Constraints
    __table_args__ = (
        UniqueConstraint("agent_id", "tool_id", name="uq_agent_tool"),
    )
```

#### 2.2.2 `agent_knowledge_base` 关联表

```python
# app/models/agent_knowledge_base.py — Phase 2 新增文件

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, DateTime, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin


class AgentKnowledgeBase(Base, UUIDPrimaryKeyMixin):
    """Agent-KnowledgeBase 多对多关联表（Phase 3 激活，Phase 2 先建表）"""
    __tablename__ = "agent_knowledge_bases"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    agent = relationship("Agent", back_populates="agent_knowledge_bases")

    # Constraints
    __table_args__ = (
        UniqueConstraint("agent_id", "knowledge_base_id", name="uq_agent_kb"),
    )
```

### 2.3 枚举扩展

```python
# app/models/enums.py — Phase 2 新增枚举

class ProviderType(str, enum.Enum):
    openai = "openai"
    anthropic = "anthropic"
    google = "google"
    custom = "custom"


class ToolType(str, enum.Enum):
    preset = "preset"
    custom = "custom"


class AuthType(str, enum.Enum):
    none = "none"
    api_key = "api_key"
    bearer = "bearer"
```

### 2.4 Alembic 迁移

```bash
alembic revision --autogenerate -m "phase2_agent_tool_model"
alembic upgrade head
```

迁移内容摘要：

1. **agents 表**：删除 `model_provider`、`model_name`、`tools`、`knowledge_base_ids` 列；新增 `model_id` 外键列
2. **tools 表**：删除 `type`、`config` 列；新增 `tool_type`、`openapi_spec`、`api_url`、`auth_type`、`auth_config` 列
3. **model_providers 表**：新增 `provider_type` 列；`enabled` 改名为 `is_enabled`
4. **model_usages 表**：新增 `provider_id`、`model_id` 外键列
5. **新建 `llm_models` 表**
6. **新建 `agent_tools` 关联表**
7. **新建 `agent_knowledge_bases` 关联表**

---

## 3. 预置数据 Seed

### 3.1 Seed 脚本 `app/core/seed.py`

Seed 在应用首次启动时自动执行（通过 lifespan 或手动触发命令）。

```python
# app/core/seed.py

"""
预置数据初始化脚本。
在数据库初始化完成后执行，插入预置 Agent 和预置工具。
幂等设计：检查 is_preset=True 的记录是否已存在，已存在则跳过。
"""

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.tool import Tool
from app.models.enums import MemoryStrategy, OutputFormat

logger = structlog.get_logger()


# ========== 预置 Agent 配置 ==========
PRESET_AGENTS = [
    {
        "name": "产品经理",
        "description": "负责需求分析、用户故事编写和 PRD 文档输出。擅长将模糊的业务需求转化为清晰的产品规格。",
        "system_prompt": """你是一位资深产品经理。你的职责：
1. 深入理解用户需求，提炼核心问题
2. 编写清晰、结构化的 PRD 文档
3. 定义用户故事和验收标准
4. 提供产品策略建议和优先级排序
5. 输出格式规范，使用 Markdown 排版

始终从用户视角出发，关注可行性和商业价值。""",
        "memory_strategy": "window",
        "output_format": "markdown",
        "temperature": 0.7,
        "max_tokens": 4096,
    },
    {
        "name": "前端工程师",
        "description": "精通 React/Vue/TypeScript 等现代前端技术栈，擅长组件化开发和 UI 交互实现。",
        "system_prompt": """你是一位资深前端工程师，精通 React、Vue、TypeScript、Tailwind CSS 等现代前端技术栈。你的职责：
1. 编写高质量、可维护的前端代码
2. 实现响应式布局和流畅的交互体验
3. 遵循组件化设计原则，代码复用
4. 关注性能优化（懒加载、虚拟列表、缓存等）
5. 输出代码包含注释和类型定义

代码风格：函数式优先，hooks 驱动，TypeScript 严格模式。""",
        "memory_strategy": "window",
        "output_format": "markdown",
        "temperature": 0.3,
        "max_tokens": 8192,
    },
    {
        "name": "后端工程师",
        "description": "精通 Python/FastAPI/Node.js 等后端技术栈，擅长 API 设计和数据库建模。",
        "system_prompt": """你是一位资深后端工程师，精通 Python、FastAPI、Node.js、PostgreSQL 等后端技术栈。你的职责：
1. 设计 RESTful API，遵循最佳实践
2. 编写高效、安全的后端服务代码
3. 设计数据库模型和查询优化
4. 关注安全性（认证、授权、输入校验、SQL 注入防护）
5. 编写单元测试和集成测试

代码风格：分层架构（Router → Service → Repository），依赖注入，异步优先。""",
        "memory_strategy": "window",
        "output_format": "markdown",
        "temperature": 0.3,
        "max_tokens": 8192,
    },
    {
        "name": "测试工程师",
        "description": "擅长测试策略制定、测试用例设计和自动化测试脚本编写。",
        "system_prompt": """你是一位资深测试工程师。你的职责：
1. 根据需求文档制定完整的测试策略
2. 设计覆盖正向、反向、边界条件的测试用例
3. 编写自动化测试脚本（pytest/Jest/Cypress）
4. 关注性能测试和安全测试
5. 输出测试报告，包含缺陷分级和优先级

测试用例格式：编号 | 前置条件 | 步骤 | 预期结果 | 优先级""",
        "memory_strategy": "window",
        "output_format": "markdown",
        "temperature": 0.4,
        "max_tokens": 4096,
    },
    {
        "name": "Code Reviewer",
        "description": "专注于代码质量审查，识别代码中的潜在问题、安全风险和改进空间。",
        "system_prompt": """你是一位严谨的代码审查专家。你的职责：
1. 审查代码质量：命名规范、代码结构、可读性
2. 识别潜在 Bug：空指针、竞态条件、资源泄漏
3. 安全审查：SQL 注入、XSS、敏感信息暴露
4. 性能审查：N+1 查询、不必要的循环、内存泄漏
5. 架构建议：设计模式、SOLID 原则、可维护性

审查输出格式：
- 🔴 严重问题（必须修复）
- 🟡 建议改进（推荐修复）
- 🟢 小建议（可选）
- ✅ 优点（值得肯定的做法）""",
        "memory_strategy": "window",
        "output_format": "markdown",
        "temperature": 0.2,
        "max_tokens": 4096,
    },
    {
        "name": "架构师",
        "description": "负责系统架构设计、技术选型、性能优化方案制定和技术债务评估。",
        "system_prompt": """你是一位资深系统架构师。你的职责：
1. 根据业务需求设计系统架构（微服务/单体/事件驱动等）
2. 进行技术选型，分析各方案的优劣
3. 设计数据流和系统交互图
4. 评估性能瓶颈，提供优化方案
5. 制定技术规范和最佳实践
6. 评估技术债务，制定偿还计划

输出架构图时使用 Mermaid 语法，确保可渲染。
始终关注：可扩展性、高可用、安全性、成本效益。""",
        "memory_strategy": "summary",
        "output_format": "markdown",
        "temperature": 0.5,
        "max_tokens": 8192,
    },
]


# ========== 预置工具配置 ==========
PRESET_TOOLS = [
    {
        "name": "网页搜索",
        "description": "搜索互联网信息，获取实时数据和最新资讯。支持关键词搜索、站点过滤等操作。",
        "tool_type": "preset",
        "openapi_spec": {
            "operationId": "web_search",
            "summary": "搜索互联网",
            "parameters": {
                "query": {"type": "string", "description": "搜索关键词", "required": True},
                "num_results": {"type": "integer", "description": "返回结果数量", "default": 10},
                "language": {"type": "string", "description": "语言偏好", "default": "zh-CN"},
            },
        },
        "api_url": None,
        "auth_type": "none",
        "auth_config": None,
    },
    {
        "name": "网页抓取",
        "description": "抓取指定 URL 的网页内容，返回提取后的纯文本。支持自动去噪和结构化提取。",
        "tool_type": "preset",
        "openapi_spec": {
            "operationId": "web_scrape",
            "summary": "抓取网页内容",
            "parameters": {
                "url": {"type": "string", "description": "目标 URL", "required": True},
                "extract_mode": {"type": "string", "description": "提取模式: full/text/markdown", "default": "markdown"},
            },
        },
        "api_url": None,
        "auth_type": "none",
        "auth_config": None,
    },
    {
        "name": "代码执行器",
        "description": "在安全沙箱环境中执行 Python 或 JavaScript 代码，返回执行结果和输出。",
        "tool_type": "preset",
        "openapi_spec": {
            "operationId": "code_execute",
            "summary": "执行代码",
            "parameters": {
                "language": {"type": "string", "description": "编程语言: python/javascript", "required": True},
                "code": {"type": "string", "description": "要执行的代码", "required": True},
                "timeout": {"type": "integer", "description": "超时时间(秒)", "default": 30},
            },
        },
        "api_url": None,
        "auth_type": "none",
        "auth_config": None,
    },
    {
        "name": "文件读写",
        "description": "在受控沙箱中读写文件，支持创建、读取、追加、列表等操作。",
        "tool_type": "preset",
        "openapi_spec": {
            "operationId": "file_operation",
            "summary": "文件操作",
            "parameters": {
                "operation": {"type": "string", "description": "操作类型: read/write/list/delete", "required": True},
                "path": {"type": "string", "description": "文件路径", "required": True},
                "content": {"type": "string", "description": "文件内容(写入时)", "required": False},
            },
        },
        "api_url": None,
        "auth_type": "none",
        "auth_config": None,
    },
    {
        "name": "HTTP 请求",
        "description": "调用任意 REST API，支持 GET/POST/PUT/DELETE 方法和自定义认证。",
        "tool_type": "preset",
        "openapi_spec": {
            "operationId": "http_request",
            "summary": "发送 HTTP 请求",
            "parameters": {
                "method": {"type": "string", "description": "HTTP 方法: GET/POST/PUT/DELETE", "required": True},
                "url": {"type": "string", "description": "请求 URL", "required": True},
                "headers": {"type": "object", "description": "请求头", "required": False},
                "body": {"type": "object", "description": "请求体", "required": False},
                "timeout": {"type": "integer", "description": "超时时间(秒)", "default": 30},
            },
        },
        "api_url": None,
        "auth_type": "none",
        "auth_config": None,
    },
    {
        "name": "JSON 解析",
        "description": "解析、转换和格式化 JSON 数据。支持 JSONPath 查询、字段映射、格式转换。",
        "tool_type": "preset",
        "openapi_spec": {
            "operationId": "json_parse",
            "summary": "JSON 处理",
            "parameters": {
                "operation": {"type": "string", "description": "操作: parse/query/transform/format", "required": True},
                "data": {"type": "string", "description": "JSON 数据", "required": True},
                "expression": {"type": "string", "description": "JSONPath 表达式(query时)", "required": False},
            },
        },
        "api_url": None,
        "auth_type": "none",
        "auth_config": None,
    },
    {
        "name": "文本处理",
        "description": "正则匹配、文本替换、拆分合并、编码转换等文本处理操作。",
        "tool_type": "preset",
        "openapi_spec": {
            "operationId": "text_process",
            "summary": "文本处理",
            "parameters": {
                "operation": {"type": "string", "description": "操作: regex/replace/split/encode/decode", "required": True},
                "text": {"type": "string", "description": "输入文本", "required": True},
                "pattern": {"type": "string", "description": "正则表达式/替换规则", "required": False},
                "options": {"type": "object", "description": "附加选项", "required": False},
            },
        },
        "api_url": None,
        "auth_type": "none",
        "auth_config": None,
    },
]


async def seed_preset_data(db: AsyncSession) -> None:
    """
    初始化预置数据。幂等设计，重复执行不会重复插入。
    """
    await _seed_preset_agents(db)
    await _seed_preset_tools(db)
    await db.commit()
    logger.info("preset_data_seeded")


async def _seed_preset_agents(db: AsyncSession) -> None:
    """插入预置 Agent（如已存在则跳过）"""
    # 检查是否已有预置 Agent
    result = await db.execute(
        select(Agent).where(Agent.is_preset == True).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        logger.info("preset_agents_already_exist, skip")
        return

    for agent_data in PRESET_AGENTS:
        agent = Agent(
            user_id=None,  # 预置 Agent 不属于任何用户，但 FK nullable 需要调整
            is_preset=True,
            **agent_data,
        )
        db.add(agent)

    logger.info("preset_agents_created", count=len(PRESET_AGENTS))


async def _seed_preset_tools(db: AsyncSession) -> None:
    """插入预置工具（如已存在则跳过）"""
    result = await db.execute(
        select(Tool).where(Tool.is_preset == True).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        logger.info("preset_tools_already_exist, skip")
        return

    for tool_data in PRESET_TOOLS:
        tool = Tool(
            user_id=None,  # 预置工具不属于任何用户
            is_preset=True,
            **tool_data,
        )
        db.add(tool)

    logger.info("preset_tools_created", count=len(PRESET_TOOLS))
```

**重要说明**：

由于预置 Agent 和工具的 `user_id` 为 `None`（不属于任何用户），需要确保 Agent 和 Tool 表的 `user_id` 列是 **nullable** 的（Phase 0 中 Tool.user_id 已经是 nullable，Agent.user_id 需要改为 nullable）。

**Agent 表 user_id 迁移**：

```python
# 在 Agent 模型中，user_id 改为 nullable
user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
    UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
)
```

### 3.2 Seed 执行方式

在 `app/main.py` 的 lifespan 中调用：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_application", app_name=settings.app_name)
    await init_redis()

    # Phase 2: 初始化预置数据
    from app.core.database import async_session_factory
    from app.core.seed import seed_preset_data
    async with async_session_factory() as session:
        await seed_preset_data(session)

    yield
    await close_redis()
    logger.info("stopping_application")
```

或者通过 CLI 命令手动执行：

```python
# app/cli.py
import asyncio
from app.core.database import async_session_factory
from app.core.seed import seed_preset_data

async def seed():
    async with async_session_factory() as session:
        await seed_preset_data(session)

if __name__ == "__main__":
    asyncio.run(seed())
```

---

## 4. 配置变更

### 4.1 `.env` 新增配置项

```env
# ---- Phase 2: Encryption ----
FERNET_KEY=<base64-encoded-32-byte-key>
# 生成方式: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# ---- Phase 2: Tool Security ----
TOOL_TEST_TIMEOUT_SECONDS=30
TOOL_TEST_ALLOWED_DOMAINS=api.openai.com,api.anthropic.com,generativelanguage.googleapis.com
TOOL_TEST_MAX_RESPONSE_SIZE=1048576
```

### 4.2 `app/core/config.py` 新增字段

```python
class Settings(BaseSettings):
    # ... Phase 0/1 已有字段 ...

    # Phase 2: Encryption
    fernet_key: str = "change-me-fernet-key"

    # Phase 2: Tool Security
    tool_test_timeout_seconds: int = 30
    tool_test_allowed_domains: list[str] = [
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com",
    ]
    tool_test_max_response_size: int = 1048576  # 1MB
```

---

## 5. 目录结构变更（Phase 2 新增/修改的文件）

```
app/
├── core/
│   ├── config.py            # 【修改】新增 Phase 2 配置字段
│   ├── encryption.py        # 【新增】Fernet 加密/解密工具
│   ├── seed.py              # 【新增】预置数据 seed 脚本
│   └── security.py          # 【不变】Phase 1 已有
├── models/
│   ├── agent.py             # 【修改】重构 model_id 外键、删除 JSONB 字段
│   ├── tool.py              # 【修改】重构字段结构
│   ├── model_provider.py    # 【修改】新增 provider_type，新增 LLMModel 模型
│   ├── agent_tool.py        # 【新增】Agent-Tool 关联表
│   ├── agent_knowledge_base.py  # 【新增】Agent-KB 关联表
│   └── enums.py             # 【修改】新增 ProviderType、AuthType 枚举
├── schemas/
│   ├── agent.py             # 【修改】完整 Agent Schema
│   ├── tool.py              # 【修改】完整 Tool Schema
│   └── model_provider.py    # 【修改】供应商 + 模型 + 用量 Schema
├── services/
│   ├── agent_service.py     # 【新增】Agent 业务逻辑
│   ├── tool_service.py      # 【新增】工具业务逻辑（含 Swagger 解析、测试调用）
│   └── model_service.py     # 【新增】模型管理业务逻辑（含加密/脱敏）
├── api/
│   └── v1/
│       ├── agents.py        # 【修改】从空骨架到完整实现
│       ├── tools.py         # 【修改】从空骨架到完整实现
│       └── models.py        # 【修改】从空骨架到完整实现
└── tests/
    ├── test_agents.py       # 【新增】
    ├── test_tools.py        # 【新增】
    └── test_models.py       # 【新增】
```

---

## 6. 安全模块设计

### 6.1 Fernet 加密工具 `app/core/encryption.py`

用于加密存储 API Key 和工具认证信息。

```python
# app/core/encryption.py

"""
Fernet 对称加密工具。
用于加密/解密 API Key、认证 Token 等敏感数据。
"""

from cryptography.fernet import Fernet, InvalidToken
from app.core.config import settings
import structlog

logger = structlog.get_logger()


def _get_fernet() -> Fernet:
    """获取 Fernet 实例"""
    key = settings.fernet_key.encode() if isinstance(settings.fernet_key, str) else settings.fernet_key
    return Fernet(key)


def encrypt_value(plain_text: str) -> str:
    """
    加密明文值。
    返回 base64 编码的加密字符串。
    """
    f = _get_fernet()
    return f.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_value(encrypted_text: str) -> str:
    """
    解密密文。
    解密失败返回空字符串（不抛出异常，避免影响列表查询）。
    """
    try:
        f = _get_fernet()
        return f.decrypt(encrypted_text.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception) as e:
        logger.warning("decrypt_failed", error=str(e))
        return ""


def mask_api_key(api_key: str) -> str:
    """
    脱敏 API Key。
    规则：显示前 3 位和后 4 位，中间用 **** 替代。
    示例：sk-abc123...xyz789 → sk-****z789
    """
    if not api_key or len(api_key) < 8:
        return "****"
    return f"{api_key[:3]}****{api_key[-4:]}"
```

**依赖安装**：

```
# requirements.txt 新增
cryptography>=42.0.0
```

### 6.2 工具测试安全限制

工具测试接口 `POST /api/tools/:id/test` 会发起真实的 HTTP 调用，需要以下安全措施：

```python
# app/core/tool_security.py

"""
工具测试调用的安全限制。
"""

import re
from urllib.parse import urlparse
from app.core.config import settings
from app.core.exceptions import AppException


def validate_tool_url(url: str) -> None:
    """
    校验工具 URL 安全性：
    1. 必须是 HTTPS（生产环境）或 HTTP localhost（开发环境）
    2. 不允许内网 IP（10.x、172.16-31.x、192.168.x、127.x 等，除 localhost 外）
    3. 不允许 file://、ftp:// 等非 HTTP 协议
    """
    parsed = urlparse(url)

    # 协议检查
    if parsed.scheme not in ("http", "https"):
        raise AppException(
            code="INVALID_TOOL_URL",
            message="仅支持 HTTP/HTTPS 协议",
            status_code=400,
        )

    hostname = parsed.hostname or ""

    # 内网 IP 检查（允许 localhost/127.0.0.1 用于开发）
    if settings.app_env == "production":
        # 生产环境禁止 HTTP
        if parsed.scheme != "https":
            raise AppException(
                code="INVALID_TOOL_URL",
                message="生产环境仅支持 HTTPS",
                status_code=400,
            )

        # 禁止内网 IP
        private_patterns = [
            r'^10\.', r'^172\.(1[6-9]|2\d|3[01])\.',
            r'^192\.168\.', r'^127\.', r'^169\.254\.',
            r'^0\.', r'^::1$', r'^fc00:', r'^fd00:',
        ]
        for pattern in private_patterns:
            if re.match(pattern, hostname):
                raise AppException(
                    code="INVALID_TOOL_URL",
                    message="不允许访问内网地址",
                    status_code=400,
                )


def check_timeout(timeout: int) -> None:
    """校验超时设置"""
    if timeout > settings.tool_test_timeout_seconds:
        raise AppException(
            code="TIMEOUT_TOO_LARGE",
            message=f"超时时间不能超过 {settings.tool_test_timeout_seconds} 秒",
            status_code=400,
        )
```

---

## 7. API 完整规格

### 7.0 通用约定

#### 成功响应格式

所有成功响应统一使用以下格式（与 Phase 1 一致）：

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

#### 认证方式

所有接口都需要在请求头中携带有效的 access_token：

```
Authorization: Bearer <access_token>
```

#### 预置资源规则

- 预置 Agent / 预置工具：`is_preset=true`，`user_id=NULL`
- 所有用户可见预置资源（只读）
- 预置资源不可修改、不可删除
- 预置 Agent 可以「复制为自定义」（`POST /api/agents/:id/copy`）
- 预置工具不可复制（内置功能，用户直接使用）

---

### 7.1 Agent 管理 API

#### 7.1.1 获取 Agent 列表

**`GET /api/agents`**

**描述**：获取当前用户可见的 Agent 列表（预置 + 自定义），支持搜索和分页。

**权限**：需要登录。

**查询参数**：

```python
# app/schemas/agent.py

from pydantic import BaseModel, Field
from typing import Optional


class AgentListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    keyword: Optional[str] = Field(default=None, max_length=100)
    # keyword 模糊匹配 name 和 description
    is_preset: Optional[bool] = None
    # 不传：返回全部；true：仅预置；false：仅自定义
```

**业务逻辑**：

1. 获取当前用户
2. 构建查询：`WHERE user_id = current_user.id OR is_preset = true`
3. 如有 `keyword`：`AND (name ILIKE '%keyword%' OR description ILIKE '%keyword%')`
4. 如有 `is_preset` 筛选：`AND is_preset = :is_preset`
5. 按 `is_preset DESC, created_at DESC` 排序（预置排前面）
6. 分页查询，返回总数和分页数据
7. 对每个 Agent，查询其关联的 tool 数量（`COUNT(agent_tools)`）

**响应体 Schema**：

```python
class AgentListItem(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model_id: Optional[uuid.UUID] = None
    model_name: Optional[str] = None  # 冗余，从 llm_models 表联查
    memory_strategy: str
    output_format: str
    temperature: float
    max_tokens: int
    is_preset: bool
    tool_count: int = 0  # 关联的工具数量
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentListResponse(BaseModel):
    items: list[AgentListItem]
    total: int
    page: int
    page_size: int
    has_next: bool
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 401 | `UNAUTHORIZED` | 未登录 |

---

#### 7.1.2 获取 Agent 详情

**`GET /api/agents/:id`**

**描述**：获取指定 Agent 的完整详情，包含关联的工具列表。

**权限**：需要登录。仅能查看自己的自定义 Agent 和所有预置 Agent。

**业务逻辑**：

1. 获取当前用户
2. 根据 `id` 查询 Agent
   - 若不存在 → 404 `AGENT_NOT_FOUND`
3. 权限检查：
   - 若 `agent.is_preset = true` → 任何用户可查看
   - 若 `agent.is_preset = false` 且 `agent.user_id != current_user.id` → 403 `FORBIDDEN`
4. 查询关联的工具列表：通过 `agent_tools` 关联表 JOIN `tools` 表
5. 查询关联的知识库列表：通过 `agent_knowledge_bases` 关联表（Phase 2 暂返回空列表）
6. 查询关联的模型信息：通过 `model_id` JOIN `llm_models` 表 + `model_providers` 表

**响应体 Schema**：

```python
class AgentToolBrief(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    tool_type: str

    model_config = {"from_attributes": True}


class AgentDetailResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model_id: Optional[uuid.UUID] = None
    model_info: Optional[dict] = None  # {"id": ..., "model_name": ..., "provider_name": ...}
    memory_strategy: str
    output_format: str
    temperature: float
    max_tokens: int
    is_preset: bool
    tools: list[AgentToolBrief] = []
    knowledge_base_ids: list[uuid.UUID] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `AGENT_NOT_FOUND` | Agent 不存在 |
| 403 | `FORBIDDEN` | 无权查看他人的自定义 Agent |
| 401 | `UNAUTHORIZED` | 未登录 |

---

#### 7.1.3 创建自定义 Agent

**`POST /api/agents`**

**描述**：创建自定义 Agent。

**权限**：需要登录。

**请求体 Schema**：

```python
class AgentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    system_prompt: Optional[str] = Field(default=None, max_length=50000)
    model_id: Optional[uuid.UUID] = None
    memory_strategy: str = Field(default="none", pattern="^(none|window|summary)$")
    output_format: str = Field(default="markdown", pattern="^(json|markdown|text)$")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=128000)
    tool_ids: list[uuid.UUID] = Field(default_factory=list)
    # 关联的工具 ID 列表


class AgentCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    message: str = "Agent 创建成功"
```

**业务逻辑**：

1. 获取当前用户
2. 校验请求体（Pydantic 自动）
3. 若提供了 `model_id`：
   - 查询 `llm_models` 表确认模型存在且 `is_enabled=true`
   - 确认模型所属的 provider 的 `user_id == current_user.id` 且 `is_enabled=true`
   - 若不满足 → 400 `INVALID_MODEL_ID`
4. 校验 `tool_ids` 中的每个工具 ID：
   - 预置工具（`is_preset=true`）：任何用户可使用
   - 自定义工具：必须是当前用户自己的
   - 若有无效 ID → 400 `INVALID_TOOL_IDS`，details 中列出无效的 ID
5. 创建 Agent 记录：`user_id=current_user.id`, `is_preset=false`
6. 批量创建 `agent_tools` 关联记录
7. 返回新 Agent 的 ID

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 400 | `INVALID_MODEL_ID` | 指定的模型不存在或未启用 |
| 400 | `INVALID_TOOL_IDS` | 部分工具 ID 无效 |
| 401 | `UNAUTHORIZED` | 未登录 |
| 422 | `VALIDATION_ERROR` | 参数校验失败 |

---

#### 7.1.4 更新自定义 Agent

**`PUT /api/agents/:id`**

**描述**：更新自定义 Agent 配置。

**权限**：需要登录。仅能更新自己的自定义 Agent。

**请求体 Schema**：

```python
class AgentUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    system_prompt: Optional[str] = Field(default=None, max_length=50000)
    model_id: Optional[uuid.UUID] = None
    memory_strategy: Optional[str] = Field(default=None, pattern="^(none|window|summary)$")
    output_format: Optional[str] = Field(default=None, pattern="^(json|markdown|text)$")
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=128000)
    tool_ids: Optional[list[uuid.UUID]] = None
    # 传空列表 [] 表示清除所有工具关联
    # 不传 None 表示不修改工具关联
```

**业务逻辑**：

1. 获取当前用户
2. 查询 Agent
   - 不存在 → 404 `AGENT_NOT_FOUND`
3. 权限检查：
   - `agent.is_preset = true` → 403 `PRESET_AGENT_READONLY`（预置 Agent 不可修改）
   - `agent.user_id != current_user.id` → 403 `FORBIDDEN`
4. 若请求中有 `model_id`，校验模型（同创建逻辑）
5. 若请求中有 `tool_ids`，校验工具 ID（同创建逻辑）
6. 更新 Agent 字段（仅更新非 None 的字段）
7. 若提供了 `tool_ids`：
   - 删除旧的 `agent_tools` 关联
   - 批量创建新的 `agent_tools` 关联
8. 返回更新后的 Agent 信息

**响应体 Schema**：

```python
class AgentUpdateResponse(BaseModel):
    id: uuid.UUID
    name: str
    message: str = "Agent 更新成功"
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `AGENT_NOT_FOUND` | Agent 不存在 |
| 403 | `PRESET_AGENT_READONLY` | 预置 Agent 不可修改 |
| 403 | `FORBIDDEN` | 无权修改他人 Agent |
| 400 | `INVALID_MODEL_ID` | 指定的模型不存在或未启用 |
| 400 | `INVALID_TOOL_IDS` | 部分工具 ID 无效 |
| 401 | `UNAUTHORIZED` | 未登录 |

---

#### 7.1.5 删除自定义 Agent

**`DELETE /api/agents/:id`**

**描述**：删除自定义 Agent。

**权限**：需要登录。仅能删除自己的自定义 Agent。

**业务逻辑**：

1. 获取当前用户
2. 查询 Agent
   - 不存在 → 404 `AGENT_NOT_FOUND`
3. 权限检查：
   - `agent.is_preset = true` → 403 `PRESET_AGENT_NOT_DELETABLE`
   - `agent.user_id != current_user.id` → 403 `FORBIDDEN`
4. 删除 Agent（`cascade="all, delete-orphan"` 会自动删除关联的 `agent_tools` 和 `agent_knowledge_bases`）
5. 返回成功响应

**响应体 Schema**：

```python
class AgentDeleteResponse(BaseModel):
    message: str = "Agent 已删除"
    agent_id: uuid.UUID
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `AGENT_NOT_FOUND` | Agent 不存在 |
| 403 | `PRESET_AGENT_NOT_DELETABLE` | 预置 Agent 不可删除 |
| 403 | `FORBIDDEN` | 无权删除他人 Agent |
| 401 | `UNAUTHORIZED` | 未登录 |

---

#### 7.1.6 复制预置 Agent

**`POST /api/agents/:id/copy`**

**描述**：将预置 Agent 复制为自定义 Agent。复制所有配置，改名，`is_preset=false`，`user_id=当前用户`。

**权限**：需要登录。仅能复制预置 Agent。

**请求体 Schema**：

```python
class AgentCopyRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    # 自定义名称，不传则使用 "预置名 - 副本"
```

**业务逻辑**：

1. 获取当前用户
2. 查询源 Agent
   - 不存在 → 404 `AGENT_NOT_FOUND`
3. 检查 `agent.is_preset == true`
   - 若不是 → 400 `ONLY_PRESET_CAN_COPY`（仅预置 Agent 可复制）
4. 确定新名称：`request.name` 或 `f"{agent.name} - 副本"`
5. 创建新的 Agent 记录：
   - 复制所有配置字段（`description`、`system_prompt`、`model_id`、`memory_strategy`、`output_format`、`temperature`、`max_tokens`）
   - `user_id = current_user.id`
   - `is_preset = false`
6. 复制 `agent_tools` 关联（查询源 Agent 关联的工具 ID 列表，批量创建新关联）
7. 返回新 Agent 信息

**响应体 Schema**：

```python
class AgentCopyResponse(BaseModel):
    id: uuid.UUID
    name: str
    original_id: uuid.UUID
    message: str = "Agent 复制成功"
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `AGENT_NOT_FOUND` | Agent 不存在 |
| 400 | `ONLY_PRESET_CAN_COPY` | 仅预置 Agent 可复制 |
| 401 | `UNAUTHORIZED` | 未登录 |

---

### 7.2 工具管理 API

#### 7.2.1 获取工具列表

**`GET /api/tools`**

**描述**：获取当前用户可见的工具列表（预置 + 自定义），支持搜索和分页。

**权限**：需要登录。

**查询参数**：

```python
class ToolListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    keyword: Optional[str] = Field(default=None, max_length=100)
    tool_type: Optional[str] = Field(default=None, pattern="^(preset|custom)$")
```

**业务逻辑**：

1. 获取当前用户
2. 构建查询：`WHERE user_id = current_user.id OR is_preset = true`
3. 如有 `keyword`：`AND (name ILIKE '%keyword%' OR description ILIKE '%keyword%')`
4. 如有 `tool_type` 筛选：`AND tool_type = :tool_type`
5. 排序：`is_preset DESC, name ASC`
6. 分页查询
7. 对每个工具查询被 Agent 引用的数量：`COUNT(agent_tools)`

**响应体 Schema**：

```python
class ToolListItem(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    tool_type: str
    is_preset: bool
    agent_count: int = 0  # 被多少 Agent 引用
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ToolListResponse(BaseModel):
    items: list[ToolListItem]
    total: int
    page: int
    page_size: int
    has_next: bool
```

---

#### 7.2.2 获取工具详情

**`GET /api/tools/:id`**

**描述**：获取指定工具的完整详情。

**权限**：需要登录。预置工具所有人可见，自定义工具仅 owner 可见。

**业务逻辑**：

1. 获取当前用户
2. 查询 Tool
   - 不存在 → 404 `TOOL_NOT_FOUND`
3. 权限检查：
   - `tool.is_preset = true` → 所有人可见
   - `tool.user_id != current_user.id` → 403 `FORBIDDEN`
4. 返回完整详情（含 `openapi_spec`、`api_url`、`auth_type`，但 `auth_config` 中的敏感信息脱敏）

**响应体 Schema**：

```python
class ToolDetailResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    name: str
    description: Optional[str] = None
    tool_type: str
    is_preset: bool
    openapi_spec: Optional[dict] = None
    api_url: Optional[str] = None
    auth_type: str
    # auth_config 脱敏返回：仅显示类型，不显示实际值
    auth_config_summary: Optional[dict] = None
    # 如 {"type": "api_key", "header_name": "X-API-Key", "has_value": true}
    agent_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

---

#### 7.2.3 创建自定义工具

**`POST /api/tools`**

**描述**：创建自定义工具，支持通过 OpenAPI/Swagger JSON 导入。

**权限**：需要登录。

**请求体 Schema**：

```python
class ToolCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    api_url: str = Field(..., min_length=1, max_length=2048)
    # 工具的 API 端点 URL
    openapi_spec: Optional[dict] = None
    # OpenAPI 3.0 规范 JSON，可选
    auth_type: str = Field(default="none", pattern="^(none|api_key|bearer)$")
    auth_config: Optional[dict] = None
    # auth_type=api_key: {"header_name": "X-API-Key", "api_key_value": "sk-xxx"}
    # auth_type=bearer: {"token": "eyJhbGci..."}

    @field_validator("api_url")
    @classmethod
    def validate_api_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("api_url 必须以 http:// 或 https:// 开头")
        return v
```

**业务逻辑**：

1. 获取当前用户
2. 校验请求体
3. 若提供 `openapi_spec`，进行基本格式校验：
   - 检查是否为有效的 OpenAPI 3.0 规范（至少包含 `openapi` 版本字段和 `paths` 或 `operationId`）
   - 若不合法 → 400 `INVALID_OPENAPI_SPEC`
4. 处理认证配置：
   - `auth_type=api_key`：从 `auth_config` 中取 `api_key_value`，使用 Fernet 加密存储为 `api_key_value_encrypted`，同时保留 `header_name`
   - `auth_type=bearer`：从 `auth_config` 中取 `token`，加密存储为 `token_encrypted`
   - `auth_type=none`：`auth_config=None`
5. 创建 Tool 记录
6. 返回新工具 ID

**响应体 Schema**：

```python
class ToolCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    message: str = "工具创建成功"
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 400 | `INVALID_OPENAPI_SPEC` | OpenAPI 规范格式无效 |
| 400 | `INVALID_AUTH_CONFIG` | 认证配置格式错误 |
| 401 | `UNAUTHORIZED` | 未登录 |
| 422 | `VALIDATION_ERROR` | 参数校验失败 |

---

#### 7.2.4 更新自定义工具

**`PUT /api/tools/:id`**

**描述**：更新自定义工具配置。

**权限**：需要登录。仅能更新自己的自定义工具。

**请求体 Schema**：

```python
class ToolUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    api_url: Optional[str] = Field(default=None, max_length=2048)
    openapi_spec: Optional[dict] = None
    auth_type: Optional[str] = Field(default=None, pattern="^(none|api_key|bearer)$")
    auth_config: Optional[dict] = None
    # 更新认证配置时，需要重新提供完整值（不支持部分更新）
```

**业务逻辑**：

1. 获取当前用户
2. 查询 Tool
   - 不存在 → 404 `TOOL_NOT_FOUND`
3. 权限检查：
   - `tool.is_preset = true` → 403 `PRESET_TOOL_NOT_EDITABLE`
   - `tool.user_id != current_user.id` → 403 `FORBIDDEN`
4. 校验更新字段（同创建逻辑）
5. 若更新 `auth_config`，重新加密存储
6. 更新 Tool 记录
7. 返回更新后的工具信息

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `TOOL_NOT_FOUND` | 工具不存在 |
| 403 | `PRESET_TOOL_NOT_EDITABLE` | 预置工具不可修改 |
| 403 | `FORBIDDEN` | 无权修改他人工具 |
| 400 | `INVALID_AUTH_CONFIG` | 认证配置格式错误 |

---

#### 7.2.5 删除自定义工具

**`DELETE /api/tools/:id`**

**描述**：删除自定义工具。返回引用该工具的 Agent 数量。

**权限**：需要登录。仅能删除自己的自定义工具。

**业务逻辑**：

1. 获取当前用户
2. 查询 Tool
   - 不存在 → 404 `TOOL_NOT_FOUND`
3. 权限检查：
   - `tool.is_preset = true` → 403 `PRESET_TOOL_NOT_DELETABLE`
   - `tool.user_id != current_user.id` → 403 `FORBIDDEN`
4. 查询引用数量：`SELECT COUNT(*) FROM agent_tools WHERE tool_id = :id`
5. 若 `force=true`（查询参数）：
   - 删除 `agent_tools` 关联记录
   - 删除 Tool 记录
6. 若 `force` 未传或 `force=false`：
   - 不执行删除，仅返回引用数量
   - 前端根据引用数量决定是否弹出确认弹窗后带 `force=true` 再次请求
7. 返回删除结果

**查询参数**：

```python
class ToolDeleteParams(BaseModel):
    force: bool = Field(default=False)
```

**响应体 Schema**：

```python
class ToolDeleteResponse(BaseModel):
    message: str
    agent_count: int  # 引用此工具的 Agent 数量
    deleted: bool     # 是否已实际删除
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `TOOL_NOT_FOUND` | 工具不存在 |
| 403 | `PRESET_TOOL_NOT_DELETABLE` | 预置工具不可删除 |
| 403 | `FORBIDDEN` | 无权删除他人工具 |

---

#### 7.2.6 测试调用工具

**`POST /api/tools/:id/test`**

**描述**：传入参数，后端真正发起 HTTP 调用，返回结果。用于验证自定义工具是否可用。

**权限**：需要登录。仅能测试自己的自定义工具或预置工具。

**请求体 Schema**：

```python
class ToolTestRequest(BaseModel):
    parameters: dict = Field(..., description="工具调用参数，key-value 形式")
    timeout: int = Field(default=30, ge=1, le=60)
```

**业务逻辑**：

1. 获取当前用户
2. 查询 Tool
   - 不存在 → 404 `TOOL_NOT_FOUND`
3. 权限检查：预置工具或自己的工具
4. 对 `api_url` 进行安全校验（`validate_tool_url`）
5. 校验 `timeout`（`check_timeout`）
6. 构建 HTTP 请求：
   - 根据 `openapi_spec` 解析参数，组装请求
   - 根据 `auth_type` 添加认证头：
     - `none`：无认证头
     - `api_key`：解密 `auth_config`，添加 `{header_name: decrypted_value}`
     - `bearer`：解密 `auth_config`，添加 `Authorization: Bearer {decrypted_token}`
7. 使用 `httpx.AsyncClient` 发起 HTTP 请求（异步，设置超时）
8. 捕获响应：
   - 成功：返回 `status_code`、`response_body`（截断到 `max_response_size`）
   - 失败：返回 `status_code`、`error_message`
   - 超时：返回 `timeout` 错误
   - 网络错误：返回连接错误信息
9. 记录测试日志（可选）

**响应体 Schema**：

```python
class ToolTestResponse(BaseModel):
    success: bool
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `TOOL_NOT_FOUND` | 工具不存在 |
| 403 | `FORBIDDEN` | 无权测试他人工具 |
| 400 | `INVALID_TOOL_URL` | URL 不安全 |
| 400 | `TIMEOUT_TOO_LARGE` | 超时设置过大 |
| 408 | `TOOL_TEST_TIMEOUT` | 工具调用超时 |

---

### 7.3 模型管理 API

#### 7.3.1 获取供应商列表

**`GET /api/models/providers`**

**描述**：获取当前用户配置的所有模型供应商。

**权限**：需要登录。

**业务逻辑**：

1. 获取当前用户
2. 查询 `model_providers` 表：`WHERE user_id = current_user.id`
3. 对每个供应商，API Key 脱敏显示
4. 对每个供应商，查询其下的模型数量和已启用模型数量

**响应体 Schema**：

```python
class ProviderListItem(BaseModel):
    id: uuid.UUID
    provider_name: str
    provider_type: str
    base_url: Optional[str] = None
    api_key_masked: str  # 脱敏后的 API Key
    is_enabled: bool
    model_count: int = 0        # 总模型数
    enabled_model_count: int = 0  # 已启用模型数
    has_default_model: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class ProviderListResponse(BaseModel):
    items: list[ProviderListItem]
```

---

#### 7.3.2 添加供应商

**`POST /api/models/providers`**

**描述**：添加模型供应商配置。

**权限**：需要登录。

**请求体 Schema**：

```python
class ProviderCreateRequest(BaseModel):
    provider_name: str = Field(..., min_length=1, max_length=100)
    provider_type: str = Field(..., pattern="^(openai|anthropic|google|custom)$")
    api_key: str = Field(..., min_length=1, max_length=1024)
    base_url: Optional[str] = Field(default=None, max_length=2048)
    # provider_type=custom 时必填
    # provider_type=openai/anthropic/google 时可选（用于覆盖默认 URL）
    models: list[str] = Field(default_factory=list)
    # 初始要启用的模型名称列表，如 ["gpt-4o", "gpt-4o-mini"]

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v, info):
        provider_type = info.data.get("provider_type")
        if provider_type == "custom" and not v:
            raise ValueError("自定义供应商必须提供 base_url")
        return v
```

**业务逻辑**：

1. 获取当前用户
2. 校验请求体
3. 使用 Fernet 加密 `api_key` → `api_key_encrypted`
4. 创建 `ModelProvider` 记录
5. 若提供了 `models` 列表，为每个模型名称创建 `LLMModel` 记录：
   - `provider_id = provider.id`
   - `model_name = model_name`
   - `is_enabled = true`
   - 根据 `model_name` 查询预定义价格表（可选，内置常见模型的价格）
6. 若该用户没有其他供应商，自动设为 `is_enabled=true`
7. 返回供应商信息

**默认 Base URL 映射**：

| provider_type | 默认 base_url |
|--------------|---------------|
| openai | `https://api.openai.com/v1` |
| anthropic | `https://api.anthropic.com` |
| google | `https://generativelanguage.googleapis.com/v1beta` |
| custom | 用户必填 |

**响应体 Schema**：

```python
class ProviderCreateResponse(BaseModel):
    id: uuid.UUID
    provider_name: str
    provider_type: str
    message: str = "供应商添加成功"
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 400 | `INVALID_PROVIDER_TYPE` | 无效的供应商类型 |
| 400 | `MISSING_BASE_URL` | 自定义供应商未提供 base_url |
| 401 | `UNAUTHORIZED` | 未登录 |

---

#### 7.3.3 更新供应商

**`PUT /api/models/providers/:id`**

**描述**：更新供应商配置（名称、API Key、base_url）。

**权限**：需要登录。仅能更新自己的供应商。

**请求体 Schema**：

```python
class ProviderUpdateRequest(BaseModel):
    provider_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    api_key: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    # 若提供，重新加密存储
    base_url: Optional[str] = Field(default=None, max_length=2048)
```

**业务逻辑**：

1. 获取当前用户
2. 查询 Provider
   - 不存在 → 404 `PROVIDER_NOT_FOUND`
   - `provider.user_id != current_user.id` → 403 `FORBIDDEN`
3. 更新字段（仅更新非 None 的）
4. 若更新 `api_key`：重新加密存储
5. 返回更新后的供应商信息

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `PROVIDER_NOT_FOUND` | 供应商不存在 |
| 403 | `FORBIDDEN` | 无权修改他人供应商 |

---

#### 7.3.4 删除供应商

**`DELETE /api/models/providers/:id`**

**描述**：删除供应商及其下所有模型配置。

**权限**：需要登录。仅能删除自己的供应商。

**业务逻辑**：

1. 获取当前用户
2. 查询 Provider（权限检查同上）
3. 查询是否有 Agent 正在使用该供应商下的模型：
   - `SELECT COUNT(*) FROM agents WHERE model_id IN (SELECT id FROM llm_models WHERE provider_id = :id)`
   - 若有引用 → 400 `PROVIDER_IN_USE`，message 中告知引用数量
4. 删除 Provider（`cascade="all, delete-orphan"` 自动删除 `llm_models` 记录）
5. 将引用该供应商下模型的 Agent 的 `model_id` 设为 `NULL`（`ondelete="SET NULL"`）
6. 返回成功响应

**响应体 Schema**：

```python
class ProviderDeleteResponse(BaseModel):
    message: str = "供应商已删除"
    provider_id: uuid.UUID
    affected_models: int  # 被删除的模型数量
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `PROVIDER_NOT_FOUND` | 供应商不存在 |
| 403 | `FORBIDDEN` | 无权删除他人供应商 |
| 400 | `PROVIDER_IN_USE` | 供应商下模型正在被 Agent 使用 |

---

#### 7.3.5 启用/禁用供应商

**`POST /api/models/providers/:id/toggle`**

**描述**：切换供应商启用/禁用状态。禁用后其下所有模型也变为不可用。

**权限**：需要登录。

**请求体**：无

**业务逻辑**：

1. 获取当前用户
2. 查询 Provider（权限检查）
3. 切换 `is_enabled` 状态：`is_enabled = NOT is_enabled`
4. 若禁用供应商，同时将其下所有模型的 `is_enabled` 设为 `false`
5. 返回最新状态

**响应体 Schema**：

```python
class ProviderToggleResponse(BaseModel):
    id: uuid.UUID
    provider_name: str
    is_enabled: bool
    message: str
```

---

#### 7.3.6 获取供应商下的模型列表

**`GET /api/models/providers/:id/models`**

**描述**：获取指定供应商下的所有模型列表。

**权限**：需要登录。

**业务逻辑**：

1. 获取当前用户
2. 查询 Provider（权限检查）
3. 查询 `llm_models` 表：`WHERE provider_id = provider.id`
4. 排序：`is_default DESC, is_enabled DESC, model_name ASC`

**响应体 Schema**：

```python
class ModelItem(BaseModel):
    id: uuid.UUID
    provider_id: uuid.UUID
    model_name: str
    display_name: Optional[str] = None
    input_price: float
    output_price: float
    is_enabled: bool
    is_default: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ModelListResponse(BaseModel):
    items: list[ModelItem]
    provider_name: str
    provider_type: str
```

---

#### 7.3.7 添加/启用模型

**`POST /api/models/providers/:id/models`**

**描述**：在指定供应商下添加新模型。

**权限**：需要登录。

**请求体 Schema**：

```python
class ModelCreateRequest(BaseModel):
    model_name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = Field(default=None, max_length=200)
    input_price: float = Field(default=0.0, ge=0.0)
    output_price: float = Field(default=0.0, ge=0.0)

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        # 仅允许字母、数字、连字符、点、下划线
        import re
        if not re.match(r'^[a-zA-Z0-9.\-_]+$', v):
            raise ValueError("模型名称仅支持字母、数字、连字符、点和下划线")
        return v
```

**业务逻辑**：

1. 获取当前用户
2. 查询 Provider（权限检查）
3. 检查是否已存在同名模型：`WHERE provider_id = :id AND model_name = :model_name`
   - 若存在但 `is_enabled=false` → 重新启用，更新配置
   - 若存在且 `is_enabled=true` → 409 `MODEL_ALREADY_EXISTS`
4. 创建 `LLMModel` 记录
5. 返回模型信息

**响应体 Schema**：

```python
class ModelCreateResponse(BaseModel):
    id: uuid.UUID
    model_name: str
    message: str = "模型添加成功"
```

---

#### 7.3.8 更新模型配置

**`PUT /api/models/:model_id`**

**描述**：更新模型配置（显示名称、价格、启用状态）。

**权限**：需要登录。仅能更新自己供应商下的模型。

**请求体 Schema**：

```python
class ModelUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=200)
    input_price: Optional[float] = Field(default=None, ge=0.0)
    output_price: Optional[float] = Field(default=None, ge=0.0)
    is_enabled: Optional[bool] = None
```

**业务逻辑**：

1. 获取当前用户
2. 查询 LLMModel，JOIN Provider 确认 `provider.user_id == current_user.id`
   - 不存在 → 404 `MODEL_NOT_FOUND`
3. 更新字段
4. 若禁用模型，且该模型是默认模型 → 自动取消默认

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `MODEL_NOT_FOUND` | 模型不存在 |
| 403 | `FORBIDDEN` | 无权修改 |

---

#### 7.3.9 删除模型

**`DELETE /api/models/:model_id`**

**描述**：删除模型配置。

**权限**：需要登录。

**业务逻辑**：

1. 权限检查（同上）
2. 检查是否有 Agent 正在使用此模型
   - 若有 → 400 `MODEL_IN_USE`
3. 删除模型记录
4. 返回成功

**响应体 Schema**：

```python
class ModelDeleteResponse(BaseModel):
    message: str = "模型已删除"
    model_id: uuid.UUID
```

---

#### 7.3.10 设为默认模型

**`POST /api/models/:model_id/set-default`**

**描述**：将指定模型设为当前用户的默认模型。同一时间仅允许一个默认模型。

**权限**：需要登录。

**业务逻辑**：

1. 权限检查
2. 查询当前用户的所有供应商下的所有模型
3. 将所有模型的 `is_default` 设为 `false`
4. 将目标模型的 `is_default` 设为 `true`
5. 返回成功

**响应体 Schema**：

```python
class SetDefaultModelResponse(BaseModel):
    model_id: uuid.UUID
    model_name: str
    message: str = "已设为默认模型"
```

---

#### 7.3.11 用量统计

**`GET /api/models/usage`**

**描述**：查询模型使用量统计，支持按模型/按天聚合。

**权限**：需要登录。

**查询参数**：

```python
class UsageQueryParams(BaseModel):
    group_by: str = Field(default="day", pattern="^(model|day|provider)$")
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    provider_id: Optional[uuid.UUID] = None
    model_id: Optional[uuid.UUID] = None
```

**业务逻辑**：

1. 获取当前用户
2. 构建查询：`WHERE user_id = current_user.id`
3. 如有 `start_date`：`AND date >= start_date`
4. 如有 `end_date`：`AND date <= end_date`
5. 如有 `provider_id`：`AND provider_id = :provider_id`
6. 如有 `model_id`：`AND model_id = :model_id`
7. 按 `group_by` 聚合：
   - `day`：`GROUP BY date`
   - `model`：`GROUP BY model_name`
   - `provider`：`GROUP BY provider_name`
8. 统计字段：`SUM(input_tokens)`、`SUM(output_tokens)`、`SUM(cost)`
9. 计算汇总：总 token、总费用

**响应体 Schema**：

```python
class UsageItem(BaseModel):
    group_key: str  # 日期字符串/模型名/供应商名
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float
    request_count: int = 0  # 如果有记录请求数的话


class UsageSummary(BaseModel):
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cost: float
    date_range: str  # "2026-07-01 ~ 2026-07-14"


class UsageResponse(BaseModel):
    items: list[UsageItem]
    summary: UsageSummary
```

**默认行为**：不传日期时默认查最近 30 天。

---

## 8. Service 层完整定义

### 8.1 `app/services/agent_service.py`

```python
"""Agent 服务：处理 Agent 的 CRUD、复制等操作"""

import uuid
from typing import Optional

from sqlalchemy import select, func, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException
from app.models.agent import Agent
from app.models.tool import Tool
from app.models.agent_tool import AgentTool
from app.models.model_provider import LLMModel, ModelProvider
from app.models.user import User


class AgentService:

    @staticmethod
    async def list_agents(
        db: AsyncSession,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        is_preset: Optional[bool] = None,
    ) -> dict:
        """
        获取 Agent 列表（预置 + 当前用户自定义）。
        """
        # 基础查询：预置 Agent + 当前用户的 Agent
        base_condition = or_(
            Agent.is_preset == True,
            Agent.user_id == user_id,
        )
        query = select(Agent).where(base_condition)

        # 搜索
        if keyword:
            query = query.where(
                or_(
                    Agent.name.ilike(f"%{keyword}%"),
                    Agent.description.ilike(f"%{keyword}%"),
                )
            )

        # 筛选
        if is_preset is not None:
            query = query.where(Agent.is_preset == is_preset)

        # 总数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页 + 排序
        query = query.order_by(Agent.is_preset.desc(), Agent.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        agents = result.scalars().all()

        # 查询每个 Agent 的工具数量
        agent_ids = [a.id for a in agents]
        tool_counts = {}
        if agent_ids:
            count_result = await db.execute(
                select(AgentTool.agent_id, func.count(AgentTool.id))
                .where(AgentTool.agent_id.in_(agent_ids))
                .group_by(AgentTool.agent_id)
            )
            tool_counts = dict(count_result.all())

        items = []
        for agent in agents:
            item = {
                "id": agent.id,
                "name": agent.name,
                "description": agent.description,
                "system_prompt": agent.system_prompt,
                "model_id": agent.model_id,
                "memory_strategy": agent.memory_strategy,
                "output_format": agent.output_format,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
                "is_preset": agent.is_preset,
                "tool_count": tool_counts.get(agent.id, 0),
                "created_at": agent.created_at,
                "updated_at": agent.updated_at,
            }
            items.append(item)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": page * page_size < total,
        }

    @staticmethod
    async def get_agent_detail(
        db: AsyncSession,
        agent_id: uuid.UUID,
        current_user: User,
    ) -> dict:
        """获取 Agent 详情，含工具列表和模型信息。"""
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()

        if agent is None:
            raise AppException(code="AGENT_NOT_FOUND", message="Agent 不存在", status_code=404)

        # 权限检查
        if not agent.is_preset and agent.user_id != current_user.id:
            raise AppException(code="FORBIDDEN", message="无权查看此 Agent", status_code=403)

        # 查询关联工具
        tool_result = await db.execute(
            select(Tool).join(AgentTool).where(AgentTool.agent_id == agent_id)
        )
        tools = tool_result.scalars().all()

        # 查询关联知识库
        # Phase 2 暂返回空列表

        # 查询模型信息
        model_info = None
        if agent.model_id:
            model_result = await db.execute(
                select(LLMModel, ModelProvider)
                .join(ModelProvider, LLMModel.provider_id == ModelProvider.id)
                .where(LLMModel.id == agent.model_id)
            )
            row = model_result.one_or_none()
            if row:
                model, provider = row
                model_info = {
                    "id": str(model.id),
                    "model_name": model.model_name,
                    "display_name": model.display_name,
                    "provider_name": provider.provider_name,
                    "provider_type": provider.provider_type,
                }

        return {
            "id": agent.id,
            "user_id": agent.user_id,
            "name": agent.name,
            "description": agent.description,
            "system_prompt": agent.system_prompt,
            "model_id": agent.model_id,
            "model_info": model_info,
            "memory_strategy": agent.memory_strategy,
            "output_format": agent.output_format,
            "temperature": agent.temperature,
            "max_tokens": agent.max_tokens,
            "is_preset": agent.is_preset,
            "tools": [
                {
                    "id": t.id,
                    "name": t.name,
                    "description": t.description,
                    "tool_type": t.tool_type,
                }
                for t in tools
            ],
            "knowledge_base_ids": [],
            "created_at": agent.created_at,
            "updated_at": agent.updated_at,
        }

    @staticmethod
    async def create_agent(
        db: AsyncSession,
        user_id: uuid.UUID,
        data: dict,
    ) -> Agent:
        """创建自定义 Agent。"""
        # 校验 model_id
        if data.get("model_id"):
            await AgentService._validate_model(db, data["model_id"], user_id)

        # 校验 tool_ids
        tool_ids = data.pop("tool_ids", [])
        if tool_ids:
            await AgentService._validate_tools(db, tool_ids, user_id)

        # 创建 Agent
        agent = Agent(
            user_id=user_id,
            is_preset=False,
            **{k: v for k, v in data.items() if v is not None},
        )
        db.add(agent)
        await db.flush()

        # 创建工具关联
        if tool_ids:
            for tool_id in tool_ids:
                db.add(AgentTool(agent_id=agent.id, tool_id=tool_id))

        await db.commit()
        await db.refresh(agent)
        return agent

    @staticmethod
    async def update_agent(
        db: AsyncSession,
        agent_id: uuid.UUID,
        current_user: User,
        data: dict,
    ) -> Agent:
        """更新自定义 Agent。"""
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()

        if agent is None:
            raise AppException(code="AGENT_NOT_FOUND", message="Agent 不存在", status_code=404)

        if agent.is_preset:
            raise AppException(
                code="PRESET_AGENT_READONLY",
                message="预置 Agent 不可修改",
                status_code=403,
            )

        if agent.user_id != current_user.id:
            raise AppException(code="FORBIDDEN", message="无权修改此 Agent", status_code=403)

        # 处理 tool_ids（特殊逻辑）
        tool_ids = data.pop("tool_ids", None)
        if tool_ids is not None:
            if tool_ids:
                await AgentService._validate_tools(db, tool_ids, current_user.id)

        # 校验 model_id
        if data.get("model_id"):
            await AgentService._validate_model(db, data["model_id"], current_user.id)

        # 更新字段
        for key, value in data.items():
            if value is not None:
                setattr(agent, key, value)

        # 更新工具关联
        if tool_ids is not None:
            await db.execute(
                delete(AgentTool).where(AgentTool.agent_id == agent_id)
            )
            for tool_id in tool_ids:
                db.add(AgentTool(agent_id=agent.id, tool_id=tool_id))

        await db.commit()
        await db.refresh(agent)
        return agent

    @staticmethod
    async def delete_agent(
        db: AsyncSession,
        agent_id: uuid.UUID,
        current_user: User,
    ) -> None:
        """删除自定义 Agent。"""
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()

        if agent is None:
            raise AppException(code="AGENT_NOT_FOUND", message="Agent 不存在", status_code=404)

        if agent.is_preset:
            raise AppException(
                code="PRESET_AGENT_NOT_DELETABLE",
                message="预置 Agent 不可删除",
                status_code=403,
            )

        if agent.user_id != current_user.id:
            raise AppException(code="FORBIDDEN", message="无权删除此 Agent", status_code=403)

        await db.delete(agent)
        await db.commit()

    @staticmethod
    async def copy_agent(
        db: AsyncSession,
        agent_id: uuid.UUID,
        current_user: User,
        new_name: Optional[str] = None,
    ) -> Agent:
        """复制预置 Agent 为自定义 Agent。"""
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()

        if agent is None:
            raise AppException(code="AGENT_NOT_FOUND", message="Agent 不存在", status_code=404)

        if not agent.is_preset:
            raise AppException(
                code="ONLY_PRESET_CAN_COPY",
                message="仅预置 Agent 可复制",
                status_code=400,
            )

        # 查询源 Agent 的工具关联
        tool_result = await db.execute(
            select(AgentTool.tool_id).where(AgentTool.agent_id == agent.id)
        )
        tool_ids = [row[0] for row in tool_result.all()]

        # 创建新 Agent
        new_agent = Agent(
            user_id=current_user.id,
            name=new_name or f"{agent.name} - 副本",
            description=agent.description,
            system_prompt=agent.system_prompt,
            model_id=agent.model_id,
            memory_strategy=agent.memory_strategy,
            output_format=agent.output_format,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
            is_preset=False,
        )
        db.add(new_agent)
        await db.flush()

        # 复制工具关联
        for tool_id in tool_ids:
            db.add(AgentTool(agent_id=new_agent.id, tool_id=tool_id))

        await db.commit()
        await db.refresh(new_agent)
        return new_agent

    # ---- 内部校验方法 ----

    @staticmethod
    async def _validate_model(
        db: AsyncSession, model_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """校验模型是否存在且可用。"""
        result = await db.execute(
            select(LLMModel, ModelProvider)
            .join(ModelProvider, LLMModel.provider_id == ModelProvider.id)
            .where(
                and_(
                    LLMModel.id == model_id,
                    LLMModel.is_enabled == True,
                    ModelProvider.user_id == user_id,
                    ModelProvider.is_enabled == True,
                )
            )
        )
        if result.one_or_none() is None:
            raise AppException(
                code="INVALID_MODEL_ID",
                message="指定的模型不存在或未启用",
                status_code=400,
            )

    @staticmethod
    async def _validate_tools(
        db: AsyncSession, tool_ids: list[uuid.UUID], user_id: uuid.UUID
    ) -> None:
        """校验工具 ID 是否有效（预置工具或自己的工具）。"""
        result = await db.execute(
            select(Tool.id).where(
                and_(
                    Tool.id.in_(tool_ids),
                    or_(Tool.is_preset == True, Tool.user_id == user_id),
                )
            )
        )
        valid_ids = set(row[0] for row in result.all())
        invalid_ids = set(tool_ids) - valid_ids
        if invalid_ids:
            raise AppException(
                code="INVALID_TOOL_IDS",
                message="部分工具 ID 无效",
                status_code=400,
                details=[{"tool_id": str(tid), "reason": "不存在或无权使用"} for tid in invalid_ids],
            )
```

### 8.2 `app/services/tool_service.py`

```python
"""工具服务：处理工具 CRUD、Swagger 解析、工具测试调用"""

import time
import uuid
from typing import Optional

import httpx
from sqlalchemy import select, func, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.encryption import encrypt_value, decrypt_value
from app.core.tool_security import validate_tool_url, check_timeout
from app.models.tool import Tool
from app.models.agent_tool import AgentTool
from app.models.user import User


class ToolService:

    @staticmethod
    async def list_tools(
        db: AsyncSession,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        tool_type: Optional[str] = None,
    ) -> dict:
        """获取工具列表。"""
        base_condition = or_(Tool.is_preset == True, Tool.user_id == user_id)
        query = select(Tool).where(base_condition)

        if keyword:
            query = query.where(
                or_(
                    Tool.name.ilike(f"%{keyword}%"),
                    Tool.description.ilike(f"%{keyword}%"),
                )
            )

        if tool_type:
            query = query.where(Tool.tool_type == tool_type)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Tool.is_preset.desc(), Tool.name.asc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        tools = result.scalars().all()

        # 查询 agent 引用数量
        tool_ids = [t.id for t in tools]
        agent_counts = {}
        if tool_ids:
            count_result = await db.execute(
                select(AgentTool.tool_id, func.count(func.distinct(AgentTool.agent_id)))
                .where(AgentTool.tool_id.in_(tool_ids))
                .group_by(AgentTool.tool_id)
            )
            agent_counts = dict(count_result.all())

        items = [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "tool_type": t.tool_type,
                "is_preset": t.is_preset,
                "agent_count": agent_counts.get(t.id, 0),
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in tools
        ]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": page * page_size < total,
        }

    @staticmethod
    async def get_tool_detail(
        db: AsyncSession,
        tool_id: uuid.UUID,
        current_user: User,
    ) -> dict:
        """获取工具详情。"""
        result = await db.execute(select(Tool).where(Tool.id == tool_id))
        tool = result.scalar_one_or_none()

        if tool is None:
            raise AppException(code="TOOL_NOT_FOUND", message="工具不存在", status_code=404)

        if not tool.is_preset and tool.user_id != current_user.id:
            raise AppException(code="FORBIDDEN", message="无权查看此工具", status_code=403)

        # 查询引用数量
        count_result = await db.execute(
            select(func.count(func.distinct(AgentTool.agent_id)))
            .where(AgentTool.tool_id == tool_id)
        )
        agent_count = count_result.scalar() or 0

        # auth_config 脱敏
        auth_config_summary = None
        if tool.auth_type == "api_key" and tool.auth_config:
            auth_config_summary = {
                "type": "api_key",
                "header_name": tool.auth_config.get("header_name", ""),
                "has_value": bool(tool.auth_config.get("api_key_value_encrypted")),
            }
        elif tool.auth_type == "bearer" and tool.auth_config:
            auth_config_summary = {
                "type": "bearer",
                "has_value": bool(tool.auth_config.get("token_encrypted")),
            }

        return {
            "id": tool.id,
            "user_id": tool.user_id,
            "name": tool.name,
            "description": tool.description,
            "tool_type": tool.tool_type,
            "is_preset": tool.is_preset,
            "openapi_spec": tool.openapi_spec,
            "api_url": tool.api_url,
            "auth_type": tool.auth_type,
            "auth_config_summary": auth_config_summary,
            "agent_count": agent_count,
            "created_at": tool.created_at,
            "updated_at": tool.updated_at,
        }

    @staticmethod
    async def create_tool(
        db: AsyncSession,
        user_id: uuid.UUID,
        data: dict,
    ) -> Tool:
        """创建自定义工具。"""
        # 处理 auth_config 加密
        auth_config = data.pop("auth_config", None)
        auth_type = data.get("auth_type", "none")
        encrypted_auth_config = None

        if auth_config and auth_type != "none":
            encrypted_auth_config = ToolService._encrypt_auth_config(auth_type, auth_config)

        tool = Tool(
            user_id=user_id,
            tool_type="custom",
            is_preset=False,
            auth_config=encrypted_auth_config,
            **{k: v for k, v in data.items() if v is not None},
        )
        db.add(tool)
        await db.commit()
        await db.refresh(tool)
        return tool

    @staticmethod
    async def update_tool(
        db: AsyncSession,
        tool_id: uuid.UUID,
        current_user: User,
        data: dict,
    ) -> Tool:
        """更新自定义工具。"""
        result = await db.execute(select(Tool).where(Tool.id == tool_id))
        tool = result.scalar_one_or_none()

        if tool is None:
            raise AppException(code="TOOL_NOT_FOUND", message="工具不存在", status_code=404)

        if tool.is_preset:
            raise AppException(
                code="PRESET_TOOL_NOT_EDITABLE",
                message="预置工具不可修改",
                status_code=403,
            )

        if tool.user_id != current_user.id:
            raise AppException(code="FORBIDDEN", message="无权修改此工具", status_code=403)

        # 处理 auth_config
        auth_config = data.pop("auth_config", None)
        auth_type = data.get("auth_type", tool.auth_type)
        if auth_config is not None:
            if auth_type != "none":
                tool.auth_config = ToolService._encrypt_auth_config(auth_type, auth_config)
            else:
                tool.auth_config = None

        for key, value in data.items():
            if value is not None:
                setattr(tool, key, value)

        await db.commit()
        await db.refresh(tool)
        return tool

    @staticmethod
    async def delete_tool(
        db: AsyncSession,
        tool_id: uuid.UUID,
        current_user: User,
        force: bool = False,
    ) -> dict:
        """删除自定义工具。"""
        result = await db.execute(select(Tool).where(Tool.id == tool_id))
        tool = result.scalar_one_or_none()

        if tool is None:
            raise AppException(code="TOOL_NOT_FOUND", message="工具不存在", status_code=404)

        if tool.is_preset:
            raise AppException(
                code="PRESET_TOOL_NOT_DELETABLE",
                message="预置工具不可删除",
                status_code=403,
            )

        if tool.user_id != current_user.id:
            raise AppException(code="FORBIDDEN", message="无权删除此工具", status_code=403)

        # 查询引用数量
        count_result = await db.execute(
            select(func.count(func.distinct(AgentTool.agent_id)))
            .where(AgentTool.tool_id == tool_id)
        )
        agent_count = count_result.scalar() or 0

        if not force:
            return {
                "message": f"有 {agent_count} 个 Agent 正在使用此工具",
                "agent_count": agent_count,
                "deleted": False,
            }

        # 强制删除
        await db.execute(delete(AgentTool).where(AgentTool.tool_id == tool_id))
        await db.delete(tool)
        await db.commit()

        return {
            "message": "工具已删除",
            "agent_count": agent_count,
            "deleted": True,
        }

    @staticmethod
    async def test_tool(
        db: AsyncSession,
        tool_id: uuid.UUID,
        current_user: User,
        parameters: dict,
        timeout: int = 30,
    ) -> dict:
        """测试调用工具。"""
        result = await db.execute(select(Tool).where(Tool.id == tool_id))
        tool = result.scalar_one_or_none()

        if tool is None:
            raise AppException(code="TOOL_NOT_FOUND", message="工具不存在", status_code=404)

        # 权限：预置工具或自己的工具
        if not tool.is_preset and tool.user_id != current_user.id:
            raise AppException(code="FORBIDDEN", message="无权测试此工具", status_code=403)

        # 获取 API URL（预置工具无 api_url，返回提示信息）
        if not tool.api_url:
            return {
                "success": False,
                "status_code": None,
                "response_body": None,
                "error_message": "预置工具不支持直接测试调用，请在 Agent 中使用",
                "duration_ms": None,
            }

        # 安全校验
        validate_tool_url(tool.api_url)
        check_timeout(timeout)

        # 构建请求头
        headers = {"Content-Type": "application/json"}
        if tool.auth_type == "api_key" and tool.auth_config:
            header_name = tool.auth_config.get("header_name", "X-API-Key")
            decrypted_key = decrypt_value(tool.auth_config.get("api_key_value_encrypted", ""))
            headers[header_name] = decrypted_key
        elif tool.auth_type == "bearer" and tool.auth_config:
            decrypted_token = decrypt_value(tool.auth_config.get("token_encrypted", ""))
            headers["Authorization"] = f"Bearer {decrypted_token}"

        # 发起 HTTP 请求
        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(verify=True) as client:
                response = await client.post(
                    tool.api_url,
                    json=parameters,
                    headers=headers,
                    timeout=timeout,
                )

            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            response_body = response.text

            # 截断过长的响应
            max_size = 1048576  # 1MB
            if len(response_body) > max_size:
                response_body = response_body[:max_size] + "\n... [truncated]"

            return {
                "success": 200 <= response.status_code < 300,
                "status_code": response.status_code,
                "response_body": response_body,
                "error_message": None,
                "duration_ms": duration_ms,
            }

        except httpx.TimeoutException:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "success": False,
                "status_code": 408,
                "response_body": None,
                "error_message": f"请求超时（{timeout}秒）",
                "duration_ms": duration_ms,
            }
        except httpx.RequestError as e:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "success": False,
                "status_code": None,
                "response_body": None,
                "error_message": f"网络错误: {str(e)}",
                "duration_ms": duration_ms,
            }

    # ---- 内部方法 ----

    @staticmethod
    def _encrypt_auth_config(auth_type: str, auth_config: dict) -> dict:
        """加密 auth_config 中的敏感值。"""
        if auth_type == "api_key":
            api_key_value = auth_config.get("api_key_value")
            if not api_key_value:
                raise AppException(
                    code="INVALID_AUTH_CONFIG",
                    message="api_key 认证必须提供 api_key_value",
                    status_code=400,
                )
            return {
                "header_name": auth_config.get("header_name", "X-API-Key"),
                "api_key_value_encrypted": encrypt_value(api_key_value),
            }
        elif auth_type == "bearer":
            token = auth_config.get("token")
            if not token:
                raise AppException(
                    code="INVALID_AUTH_CONFIG",
                    message="bearer 认证必须提供 token",
                    status_code=400,
                )
            return {
                "token_encrypted": encrypt_value(token),
            }
        return None
```

### 8.3 `app/services/model_service.py`

```python
"""模型管理服务：供应商 CRUD、模型配置、API Key 加密/脱敏、用量统计"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.encryption import encrypt_value, decrypt_value, mask_api_key
from app.models.model_provider import ModelProvider, LLMModel, ModelUsage
from app.models.agent import Agent
from app.models.user import User


# 常见模型预定义价格（每百万 token，USD）
PRESET_MODEL_PRICES = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
}


class ModelService:

    @staticmethod
    async def list_providers(
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[dict]:
        """获取供应商列表。"""
        result = await db.execute(
            select(ModelProvider)
            .where(ModelProvider.user_id == user_id)
            .order_by(ModelProvider.created_at.desc())
        )
        providers = result.scalars().all()

        items = []
        for p in providers:
            # 查模型数量
            model_count_result = await db.execute(
                select(func.count(LLMModel.id)).where(LLMModel.provider_id == p.id)
            )
            model_count = model_count_result.scalar() or 0

            enabled_model_count_result = await db.execute(
                select(func.count(LLMModel.id)).where(
                    and_(LLMModel.provider_id == p.id, LLMModel.is_enabled == True)
                )
            )
            enabled_model_count = enabled_model_count_result.scalar() or 0

            has_default_result = await db.execute(
                select(func.count(LLMModel.id)).where(
                    and_(LLMModel.provider_id == p.id, LLMModel.is_default == True)
                )
            )
            has_default = (has_default_result.scalar() or 0) > 0

            # 解密 API Key 后脱敏
            decrypted_key = decrypt_value(p.api_key_encrypted)
            masked_key = mask_api_key(decrypted_key)

            items.append({
                "id": p.id,
                "provider_name": p.provider_name,
                "provider_type": p.provider_type,
                "base_url": p.base_url,
                "api_key_masked": masked_key,
                "is_enabled": p.is_enabled,
                "model_count": model_count,
                "enabled_model_count": enabled_model_count,
                "has_default_model": has_default,
                "created_at": p.created_at,
            })

        return items

    @staticmethod
    async def create_provider(
        db: AsyncSession,
        user_id: uuid.UUID,
        data: dict,
    ) -> ModelProvider:
        """添加供应商。"""
        # 加密 API Key
        api_key_plain = data.pop("api_key")
        api_key_encrypted = encrypt_value(api_key_plain)

        # 默认 base_url
        provider_type = data.get("provider_type")
        base_url = data.get("base_url")
        if not base_url:
            default_urls = {
                "openai": "https://api.openai.com/v1",
                "anthropic": "https://api.anthropic.com",
                "google": "https://generativelanguage.googleapis.com/v1beta",
            }
            base_url = default_urls.get(provider_type)

        provider = ModelProvider(
            user_id=user_id,
            api_key_encrypted=api_key_encrypted,
            base_url=base_url,
            is_enabled=True,
            **{k: v for k, v in data.items() if v is not None},
        )
        db.add(provider)
        await db.flush()

        # 创建初始模型
        model_names = data.get("models", [])
        for model_name in model_names:
            prices = PRESET_MODEL_PRICES.get(model_name, {"input": 0, "output": 0})
            model = LLMModel(
                provider_id=provider.id,
                model_name=model_name,
                display_name=model_name,
                input_price=Decimal(str(prices["input"])),
                output_price=Decimal(str(prices["output"])),
                is_enabled=True,
            )
            db.add(model)

        await db.commit()
        await db.refresh(provider)
        return provider

    @staticmethod
    async def update_provider(
        db: AsyncSession,
        provider_id: uuid.UUID,
        current_user: User,
        data: dict,
    ) -> ModelProvider:
        """更新供应商。"""
        provider = await ModelService._get_provider_with_permission(db, provider_id, current_user.id)

        if data.get("api_key"):
            provider.api_key_encrypted = encrypt_value(data.pop("api_key"))

        for key, value in data.items():
            if value is not None:
                setattr(provider, key, value)

        await db.commit()
        await db.refresh(provider)
        return provider

    @staticmethod
    async def delete_provider(
        db: AsyncSession,
        provider_id: uuid.UUID,
        current_user: User,
    ) -> dict:
        """删除供应商。"""
        provider = await ModelService._get_provider_with_permission(db, provider_id, current_user.id)

        # 检查是否有 Agent 正在使用
        model_ids_result = await db.execute(
            select(LLMModel.id).where(LLMModel.provider_id == provider_id)
        )
        model_ids = [row[0] for row in model_ids_result.all()]

        if model_ids:
            agent_count_result = await db.execute(
                select(func.count(Agent.id)).where(Agent.model_id.in_(model_ids))
            )
            agent_count = agent_count_result.scalar() or 0
            if agent_count > 0:
                raise AppException(
                    code="PROVIDER_IN_USE",
                    message=f"有 {agent_count} 个 Agent 正在使用此供应商下的模型",
                    status_code=400,
                )

        affected_models = len(model_ids)
        await db.delete(provider)  # cascade 自动删除 models
        await db.commit()

        return {
            "message": "供应商已删除",
            "provider_id": provider_id,
            "affected_models": affected_models,
        }

    @staticmethod
    async def toggle_provider(
        db: AsyncSession,
        provider_id: uuid.UUID,
        current_user: User,
    ) -> dict:
        """切换供应商启用/禁用。"""
        provider = await ModelService._get_provider_with_permission(db, provider_id, current_user.id)

        provider.is_enabled = not provider.is_enabled

        # 禁用时同时禁用所有模型
        if not provider.is_enabled:
            await db.execute(
                update(LLMModel)
                .where(LLMModel.provider_id == provider_id)
                .values(is_enabled=False)
            )

        await db.commit()
        await db.refresh(provider)

        status_text = "已启用" if provider.is_enabled else "已禁用"
        return {
            "id": provider.id,
            "provider_name": provider.provider_name,
            "is_enabled": provider.is_enabled,
            "message": f"供应商{status_text}",
        }

    @staticmethod
    async def list_models(
        db: AsyncSession,
        provider_id: uuid.UUID,
        current_user: User,
    ) -> dict:
        """获取供应商下的模型列表。"""
        provider = await ModelService._get_provider_with_permission(db, provider_id, current_user.id)

        result = await db.execute(
            select(LLMModel)
            .where(LLMModel.provider_id == provider_id)
            .order_by(LLMModel.is_default.desc(), LLMModel.is_enabled.desc(), LLMModel.model_name.asc())
        )
        models = result.scalars().all()

        return {
            "items": [
                {
                    "id": m.id,
                    "provider_id": m.provider_id,
                    "model_name": m.model_name,
                    "display_name": m.display_name,
                    "input_price": float(m.input_price),
                    "output_price": float(m.output_price),
                    "is_enabled": m.is_enabled,
                    "is_default": m.is_default,
                    "created_at": m.created_at,
                }
                for m in models
            ],
            "provider_name": provider.provider_name,
            "provider_type": provider.provider_type,
        }

    @staticmethod
    async def create_model(
        db: AsyncSession,
        provider_id: uuid.UUID,
        current_user: User,
        data: dict,
    ) -> LLMModel:
        """在供应商下添加模型。"""
        provider = await ModelService._get_provider_with_permission(db, provider_id, current_user.id)

        # 检查是否已存在
        existing = await db.execute(
            select(LLMModel).where(
                and_(
                    LLMModel.provider_id == provider_id,
                    LLMModel.model_name == data["model_name"],
                )
            )
        )
        existing_model = existing.scalar_one_or_none()

        if existing_model:
            if existing_model.is_enabled:
                raise AppException(
                    code="MODEL_ALREADY_EXISTS",
                    message="该模型已存在且已启用",
                    status_code=409,
                )
            else:
                # 重新启用
                existing_model.is_enabled = True
                for key, value in data.items():
                    if value is not None:
                        setattr(existing_model, key, value)
                await db.commit()
                await db.refresh(existing_model)
                return existing_model

        model = LLMModel(
            provider_id=provider_id,
            **{k: v for k, v in data.items() if v is not None},
            is_enabled=True,
        )
        db.add(model)
        await db.commit()
        await db.refresh(model)
        return model

    @staticmethod
    async def update_model(
        db: AsyncSession,
        model_id: uuid.UUID,
        current_user: User,
        data: dict,
    ) -> LLMModel:
        """更新模型配置。"""
        result = await db.execute(
            select(LLMModel)
            .join(ModelProvider, LLMModel.provider_id == ModelProvider.id)
            .where(
                and_(LLMModel.id == model_id, ModelProvider.user_id == current_user.id)
            )
        )
        model = result.scalar_one_or_none()

        if model is None:
            raise AppException(code="MODEL_NOT_FOUND", message="模型不存在", status_code=404)

        for key, value in data.items():
            if value is not None:
                setattr(model, key, value)

        # 若禁用且是默认，取消默认
        if data.get("is_enabled") == False and model.is_default:
            model.is_default = False

        await db.commit()
        await db.refresh(model)
        return model

    @staticmethod
    async def delete_model(
        db: AsyncSession,
        model_id: uuid.UUID,
        current_user: User,
    ) -> None:
        """删除模型。"""
        result = await db.execute(
            select(LLMModel)
            .join(ModelProvider, LLMModel.provider_id == ModelProvider.id)
            .where(
                and_(LLMModel.id == model_id, ModelProvider.user_id == current_user.id)
            )
        )
        model = result.scalar_one_or_none()

        if model is None:
            raise AppException(code="MODEL_NOT_FOUND", message="模型不存在", status_code=404)

        # 检查是否有 Agent 使用
        agent_count_result = await db.execute(
            select(func.count(Agent.id)).where(Agent.model_id == model_id)
        )
        if (agent_count_result.scalar() or 0) > 0:
            raise AppException(
                code="MODEL_IN_USE",
                message="该模型正在被 Agent 使用，无法删除",
                status_code=400,
            )

        await db.delete(model)
        await db.commit()

    @staticmethod
    async def set_default_model(
        db: AsyncSession,
        model_id: uuid.UUID,
        current_user: User,
    ) -> LLMModel:
        """设为默认模型。"""
        # 获取模型（带权限检查）
        result = await db.execute(
            select(LLMModel)
            .join(ModelProvider, LLMModel.provider_id == ModelProvider.id)
            .where(
                and_(
                    LLMModel.id == model_id,
                    ModelProvider.user_id == current_user.id,
                    LLMModel.is_enabled == True,
                    ModelProvider.is_enabled == True,
                )
            )
        )
        model = result.scalar_one_or_none()

        if model is None:
            raise AppException(code="MODEL_NOT_FOUND", message="模型不存在或未启用", status_code=404)

        # 清除该用户所有模型的默认标记
        provider_ids_result = await db.execute(
            select(ModelProvider.id).where(ModelProvider.user_id == current_user.id)
        )
        provider_ids = [row[0] for row in provider_ids_result.all()]

        await db.execute(
            update(LLMModel)
            .where(LLMModel.provider_id.in_(provider_ids))
            .values(is_default=False)
        )

        # 设为默认
        model.is_default = True
        await db.commit()
        await db.refresh(model)
        return model

    @staticmethod
    async def get_usage(
        db: AsyncSession,
        user_id: uuid.UUID,
        group_by: str = "day",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        provider_id: Optional[uuid.UUID] = None,
        model_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """用量统计。"""
        # 默认最近 30 天
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # 基础查询
        query = select(ModelUsage).where(
            and_(
                ModelUsage.user_id == user_id,
                ModelUsage.date >= start_date,
                ModelUsage.date <= end_date,
            )
        )

        if provider_id:
            query = query.where(ModelUsage.provider_id == provider_id)
        if model_id:
            query = query.where(ModelUsage.model_id == model_id)

        # 聚合
        if group_by == "day":
            group_col = ModelUsage.date
        elif group_by == "model":
            group_col = ModelUsage.model_name
        elif group_by == "provider":
            group_col = ModelUsage.provider_name
        else:
            group_col = ModelUsage.date

        agg_query = (
            select(
                group_col.label("group_key"),
                func.sum(ModelUsage.input_tokens).label("input_tokens"),
                func.sum(ModelUsage.output_tokens).label("output_tokens"),
                func.sum(ModelUsage.cost).label("cost"),
            )
            .where(
                and_(
                    ModelUsage.user_id == user_id,
                    ModelUsage.date >= start_date,
                    ModelUsage.date <= end_date,
                )
            )
            .group_by(group_col)
            .order_by(group_col)
        )

        if provider_id:
            agg_query = agg_query.where(ModelUsage.provider_id == provider_id)
        if model_id:
            agg_query = agg_query.where(ModelUsage.model_id == model_id)

        result = await db.execute(agg_query)
        rows = result.all()

        items = [
            {
                "group_key": str(row.group_key),
                "input_tokens": row.input_tokens or 0,
                "output_tokens": row.output_tokens or 0,
                "total_tokens": (row.input_tokens or 0) + (row.output_tokens or 0),
                "cost": float(row.cost or 0),
            }
            for row in rows
        ]

        # 汇总
        summary = {
            "total_input_tokens": sum(i["input_tokens"] for i in items),
            "total_output_tokens": sum(i["output_tokens"] for i in items),
            "total_tokens": sum(i["total_tokens"] for i in items),
            "total_cost": sum(i["cost"] for i in items),
            "date_range": f"{start_date} ~ {end_date}",
        }

        return {"items": items, "summary": summary}

    # ---- 内部方法 ----

    @staticmethod
    async def _get_provider_with_permission(
        db: AsyncSession,
        provider_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ModelProvider:
        """获取供应商并校验权限。"""
        result = await db.execute(
            select(ModelProvider).where(
                and_(ModelProvider.id == provider_id, ModelProvider.user_id == user_id)
            )
        )
        provider = result.scalar_one_or_none()
        if provider is None:
            raise AppException(code="PROVIDER_NOT_FOUND", message="供应商不存在", status_code=404)
        return provider
```

---

## 9. 错误码汇总

### 9.1 Agent 相关

| 错误码 | HTTP 状态码 | 说明 |
|--------|-----------|------|
| `AGENT_NOT_FOUND` | 404 | Agent 不存在 |
| `FORBIDDEN` | 403 | 无权操作此 Agent |
| `PRESET_AGENT_READONLY` | 403 | 预置 Agent 不可修改 |
| `PRESET_AGENT_NOT_DELETABLE` | 403 | 预置 Agent 不可删除 |
| `ONLY_PRESET_CAN_COPY` | 400 | 仅预置 Agent 可复制 |
| `INVALID_MODEL_ID` | 400 | 指定的模型不存在或未启用 |
| `INVALID_TOOL_IDS` | 400 | 部分工具 ID 无效 |

### 9.2 Tool 相关

| 错误码 | HTTP 状态码 | 说明 |
|--------|-----------|------|
| `TOOL_NOT_FOUND` | 404 | 工具不存在 |
| `FORBIDDEN` | 403 | 无权操作此工具 |
| `PRESET_TOOL_NOT_EDITABLE` | 403 | 预置工具不可修改 |
| `PRESET_TOOL_NOT_DELETABLE` | 403 | 预置工具不可删除 |
| `INVALID_OPENAPI_SPEC` | 400 | OpenAPI 规范格式无效 |
| `INVALID_AUTH_CONFIG` | 400 | 认证配置格式错误 |
| `INVALID_TOOL_URL` | 400 | 工具 URL 不安全 |
| `TIMEOUT_TOO_LARGE` | 400 | 超时设置过大 |
| `TOOL_TEST_TIMEOUT` | 408 | 工具调用超时 |

### 9.3 Model 相关

| 错误码 | HTTP 状态码 | 说明 |
|--------|-----------|------|
| `PROVIDER_NOT_FOUND` | 404 | 供应商不存在 |
| `PROVIDER_IN_USE` | 400 | 供应商下模型正在被使用 |
| `MODEL_NOT_FOUND` | 404 | 模型不存在 |
| `MODEL_ALREADY_EXISTS` | 409 | 模型已存在且已启用 |
| `MODEL_IN_USE` | 400 | 模型正在被 Agent 使用 |
| `INVALID_PROVIDER_TYPE` | 400 | 无效的供应商类型 |
| `MISSING_BASE_URL` | 400 | 自定义供应商未提供 base_url |

---

## 10. 与 Phase 0/1 的衔接

### 10.1 路由注册

Phase 0 已在 `app/api/router.py` 中注册了空骨架路由。Phase 2 需要将空骨架替换为完整实现：

```python
# app/api/router.py — Phase 2 修改

# 注意：Phase 0 的路由前缀使用了 /v1，这里需要调整为直接使用 /api
# 根据任务要求的 API 路径清单：
api_router.include_router(agents.router, prefix="/agents", tags=["Agents"])
api_router.include_router(tools.router, prefix="/tools", tags=["Tools"])
api_router.include_router(models.router, prefix="/models", tags=["Models"])
```

### 10.2 依赖注入复用

Phase 2 复用 Phase 1 的认证依赖：

```python
from app.api.deps import get_current_user, CurrentUser, DBSession
```

### 10.3 响应格式统一

Phase 2 遵循 Phase 1 定义的统一响应格式：

```python
# 成功响应
{
    "code": 0,
    "message": "success",
    "data": { ... }
}

# 错误响应
{
    "error": {
        "code": "ERROR_CODE",
        "message": "描述",
        "details": []
    }
}
```

### 10.4 数据库事务管理

复用 Phase 0 定义的 `get_db` 依赖（自动 commit/rollback）。Service 层方法中的 `await db.commit()` 需要确保与 `get_db` 的事务管理不冲突。

**建议**：Service 层不主动 commit，由 `get_db` 的 yield 后自动 commit。仅在需要 flush 获取 ID 时调用 `await db.flush()`。

---

## 11. 测试用例

### 11.1 `tests/test_agents.py`

```python
import pytest


@pytest.mark.asyncio
class TestAgents:

    async def test_list_agents_empty(self, client, auth_headers):
        """新用户获取 Agent 列表 - 仅返回预置 Agent"""
        response = await client.get("/api/agents", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 6  # 6 个预置 Agent
        assert all(item["is_preset"] for item in data["items"])

    async def test_create_agent_success(self, client, auth_headers):
        """创建自定义 Agent"""
        response = await client.post("/api/agents", json={
            "name": "我的 Agent",
            "description": "测试用 Agent",
            "system_prompt": "You are a helpful assistant.",
            "temperature": 0.5,
            "max_tokens": 2048,
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "我的 Agent"

    async def test_create_agent_with_tools(self, client, auth_headers):
        """创建 Agent 并挂载工具"""
        # 先获取预置工具列表
        tools_resp = await client.get("/api/tools", headers=auth_headers)
        tool_ids = [t["id"] for t in tools_resp.json()["data"]["items"][:2]]

        response = await client.post("/api/agents", json={
            "name": "带工具的 Agent",
            "tool_ids": tool_ids,
        }, headers=auth_headers)
        assert response.status_code == 200

    async def test_get_preset_agent_detail(self, client, auth_headers):
        """查看预置 Agent 详情"""
        list_resp = await client.get("/api/agents?is_preset=true", headers=auth_headers)
        preset_id = list_resp.json()["data"]["items"][0]["id"]

        response = await client.get(f"/api/agents/{preset_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["is_preset"] is True

    async def test_update_preset_agent_forbidden(self, client, auth_headers):
        """修改预置 Agent - 应被拒绝"""
        list_resp = await client.get("/api/agents?is_preset=true", headers=auth_headers)
        preset_id = list_resp.json()["data"]["items"][0]["id"]

        response = await client.put(f"/api/agents/{preset_id}", json={
            "name": "Modified",
        }, headers=auth_headers)
        assert response.status_code == 403

    async def test_delete_preset_agent_forbidden(self, client, auth_headers):
        """删除预置 Agent - 应被拒绝"""
        list_resp = await client.get("/api/agents?is_preset=true", headers=auth_headers)
        preset_id = list_resp.json()["data"]["items"][0]["id"]

        response = await client.delete(f"/api/agents/{preset_id}", headers=auth_headers)
        assert response.status_code == 403

    async def test_copy_preset_agent(self, client, auth_headers):
        """复制预置 Agent 为自定义"""
        list_resp = await client.get("/api/agents?is_preset=true", headers=auth_headers)
        preset_id = list_resp.json()["data"]["items"][0]["id"]

        response = await client.post(f"/api/agents/{preset_id}/copy", json={
            "name": "我的产品经理",
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "我的产品经理"
        assert data["original_id"] == str(preset_id)

    async def test_update_custom_agent(self, client, auth_headers):
        """更新自定义 Agent"""
        # 先创建
        create_resp = await client.post("/api/agents", json={
            "name": "Test Agent",
        }, headers=auth_headers)
        agent_id = create_resp.json()["data"]["id"]

        response = await client.put(f"/api/agents/{agent_id}", json={
            "name": "Updated Agent",
            "temperature": 0.3,
        }, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Updated Agent"

    async def test_delete_custom_agent(self, client, auth_headers):
        """删除自定义 Agent"""
        create_resp = await client.post("/api/agents", json={
            "name": "To Delete",
        }, headers=auth_headers)
        agent_id = create_resp.json()["data"]["id"]

        response = await client.delete(f"/api/agents/{agent_id}", headers=auth_headers)
        assert response.status_code == 200

    async def test_create_agent_invalid_model(self, client, auth_headers):
        """创建 Agent - 使用无效 model_id"""
        import uuid
        fake_model_id = str(uuid.uuid4())

        response = await client.post("/api/agents", json={
            "name": "Bad Agent",
            "model_id": fake_model_id,
        }, headers=auth_headers)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_MODEL_ID"
```

### 11.2 `tests/test_tools.py`

```python
import pytest


@pytest.mark.asyncio
class TestTools:

    async def test_list_tools_preset(self, client, auth_headers):
        """获取工具列表 - 预置工具"""
        response = await client.get("/api/tools", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 7
        assert all(item["is_preset"] for item in data["items"])

    async def test_create_custom_tool(self, client, auth_headers):
        """创建自定义工具"""
        response = await client.post("/api/tools", json={
            "name": "My API Tool",
            "description": "调用我的 API",
            "api_url": "https://api.example.com/v1/action",
            "auth_type": "api_key",
            "auth_config": {
                "header_name": "X-API-Key",
                "api_key_value": "sk-test123456",
            },
        }, headers=auth_headers)
        assert response.status_code == 200

    async def test_delete_tool_without_force(self, client, auth_headers):
        """删除工具 - 有引用时不传 force 应返回引用数"""
        # 创建工具
        create_resp = await client.post("/api/tools", json={
            "name": "Tool to Delete",
            "api_url": "https://api.example.com",
        }, headers=auth_headers)
        tool_id = create_resp.json()["data"]["id"]

        # 先挂载到 Agent
        agent_resp = await client.post("/api/agents", json={
            "name": "Agent with Tool",
            "tool_ids": [tool_id],
        }, headers=auth_headers)

        # 不传 force 删除
        response = await client.delete(f"/api/tools/{tool_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["deleted"] is False
        assert data["agent_count"] >= 1

    async def test_delete_tool_with_force(self, client, auth_headers):
        """删除工具 - force=true 强制删除"""
        create_resp = await client.post("/api/tools", json={
            "name": "Tool Force Delete",
            "api_url": "https://api.example.com",
        }, headers=auth_headers)
        tool_id = create_resp.json()["data"]["id"]

        response = await client.delete(f"/api/tools/{tool_id}?force=true", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["deleted"] is True

    async def test_delete_preset_tool_forbidden(self, client, auth_headers):
        """删除预置工具 - 应被拒绝"""
        list_resp = await client.get("/api/tools?tool_type=preset", headers=auth_headers)
        preset_id = list_resp.json()["data"]["items"][0]["id"]

        response = await client.delete(f"/api/tools/{preset_id}?force=true", headers=auth_headers)
        assert response.status_code == 403

    async def test_test_tool_preset(self, client, auth_headers):
        """测试预置工具 - 应返回不支持直接测试"""
        list_resp = await client.get("/api/tools?tool_type=preset", headers=auth_headers)
        preset_id = list_resp.json()["data"]["items"][0]["id"]

        response = await client.post(f"/api/tools/{preset_id}/test", json={
            "parameters": {"query": "test"},
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["success"] is False  # 预置工具无 api_url
```

### 11.3 `tests/test_models.py`

```python
import pytest


@pytest.mark.asyncio
class TestModels:

    async def test_create_provider_openai(self, client, auth_headers):
        """添加 OpenAI 供应商"""
        response = await client.post("/api/models/providers", json={
            "provider_name": "OpenAI",
            "provider_type": "openai",
            "api_key": "sk-test1234567890abcdef",
            "models": ["gpt-4o", "gpt-4o-mini"],
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["provider_name"] == "OpenAI"

    async def test_create_provider_custom(self, client, auth_headers):
        """添加自定义供应商"""
        response = await client.post("/api/models/providers", json={
            "provider_name": "My Ollama",
            "provider_type": "custom",
            "api_key": "not-needed",
            "base_url": "http://localhost:11434/v1",
            "models": ["llama3", "qwen2"],
        }, headers=auth_headers)
        assert response.status_code == 200

    async def test_create_custom_provider_without_base_url(self, client, auth_headers):
        """添加自定义供应商 - 缺少 base_url"""
        response = await client.post("/api/models/providers", json={
            "provider_name": "Bad Custom",
            "provider_type": "custom",
            "api_key": "test",
        }, headers=auth_headers)
        assert response.status_code == 422  # 或 400

    async def test_list_providers_masked_key(self, client, auth_headers):
        """获取供应商列表 - API Key 应脱敏"""
        # 先创建
        await client.post("/api/models/providers", json={
            "provider_name": "OpenAI",
            "provider_type": "openai",
            "api_key": "sk-test1234567890abcdef",
        }, headers=auth_headers)

        response = await client.get("/api/models/providers", headers=auth_headers)
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert len(items) >= 1
        masked = items[0]["api_key_masked"]
        assert "****" in masked
        assert "sk-test1234567890abcdef" not in masked

    async def test_toggle_provider(self, client, auth_headers):
        """启用/禁用供应商"""
        create_resp = await client.post("/api/models/providers", json={
            "provider_name": "Test Provider",
            "provider_type": "openai",
            "api_key": "sk-test",
        }, headers=auth_headers)
        provider_id = create_resp.json()["data"]["id"]

        # 禁用
        response = await client.post(f"/api/models/providers/{provider_id}/toggle", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["is_enabled"] is False

        # 启用
        response = await client.post(f"/api/models/providers/{provider_id}/toggle", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["is_enabled"] is True

    async def test_add_model_to_provider(self, client, auth_headers):
        """添加模型到供应商"""
        create_resp = await client.post("/api/models/providers", json={
            "provider_name": "OpenAI",
            "provider_type": "openai",
            "api_key": "sk-test",
            "models": ["gpt-4o"],
        }, headers=auth_headers)
        provider_id = create_resp.json()["data"]["id"]

        response = await client.post(f"/api/models/providers/{provider_id}/models", json={
            "model_name": "gpt-4-turbo",
            "display_name": "GPT-4 Turbo",
        }, headers=auth_headers)
        assert response.status_code == 200

    async def test_set_default_model(self, client, auth_headers):
        """设置默认模型"""
        create_resp = await client.post("/api/models/providers", json={
            "provider_name": "OpenAI",
            "provider_type": "openai",
            "api_key": "sk-test",
            "models": ["gpt-4o", "gpt-4o-mini"],
        }, headers=auth_headers)
        provider_id = create_resp.json()["data"]["id"]

        # 获取模型列表
        models_resp = await client.get(f"/api/models/providers/{provider_id}/models", headers=auth_headers)
        model_id = models_resp.json()["data"]["items"][0]["id"]

        response = await client.post(f"/api/models/{model_id}/set-default", headers=auth_headers)
        assert response.status_code == 200

    async def test_usage_stats(self, client, auth_headers):
        """用量统计 - 无数据时返回空结果"""
        response = await client.get("/api/models/usage?group_by=day", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert "items" in data
        assert "summary" in data
```

---

## 12. 给 Cursor 的额外说明

### 12.1 代码生成顺序

**严格按以下顺序生成代码**：

1. **依赖安装**
   ```bash
   pip install cryptography>=42.0.0
   ```
   更新 `requirements.txt`

2. **配置变更**
   - 修改 `app/core/config.py`（新增 fernet_key、tool 安全配置）
   - 修改 `.env.example`

3. **加密工具**
   - 新建 `app/core/encryption.py`
   - 新建 `app/core/tool_security.py`

4. **枚举扩展**
   - 修改 `app/models/enums.py`

5. **模型变更**
   - 修改 `app/models/agent.py`（重构 model_id、删除 JSONB 字段）
   - 修改 `app/models/tool.py`（重构字段）
   - 修改 `app/models/model_provider.py`（新增 provider_type、LLMModel）
   - 新建 `app/models/agent_tool.py`
   - 新建 `app/models/agent_knowledge_base.py`
   - 修改 `app/models/__init__.py`（导出新模型）

6. **数据库迁移**
   ```bash
   alembic revision --autogenerate -m "phase2_agent_tool_model"
   alembic upgrade head
   ```

7. **Schema 定义**
   - 修改 `app/schemas/agent.py`
   - 修改 `app/schemas/tool.py`
   - 修改 `app/schemas/model_provider.py`

8. **预置数据 Seed**
   - 新建 `app/core/seed.py`
   - 修改 `app/main.py` lifespan（调用 seed）

9. **服务层**
   - 新建 `app/services/agent_service.py`
   - 新建 `app/services/tool_service.py`
   - 新建 `app/services/model_service.py`

10. **路由层**
    - 修改 `app/api/v1/agents.py`
    - 修改 `app/api/v1/tools.py`
    - 修改 `app/api/v1/models.py`
    - 修改 `app/api/router.py`（确认路由前缀）

11. **测试**
    - 新建 `tests/test_agents.py`
    - 新建 `tests/test_tools.py`
    - 新建 `tests/test_models.py`

### 12.2 关键约束

- **所有主键**使用 UUID v4（`uuid.uuid4()`）
- **所有时间戳**使用 UTC 时区
- **API Key** 使用 Fernet 加密存储，API 响应中绝不返回明文
- **API Key 脱敏**规则：前 3 位 + `****` + 后 4 位
- **预置资源**的 `user_id` 为 `None`，`is_preset` 为 `True`
- **预置 Agent** 的 `system_prompt` 是完整的多行字符串（见 Seed 数据）
- **预置工具** 的 `openapi_spec` 是参数定义结构（不含完整 OpenAPI 文档）
- **工具测试调用**必须经过 URL 安全校验
- **删除预置资源**一律返回 403
- **修改预置资源**一律返回 403
- **Agent 的 model_id** 指向 `llm_models` 表（不是 `model_providers`）
- **关联表使用 `cascade="all, delete-orphan"`** 确保删除 Agent/Tool 时自动清理关联

### 12.3 数据库迁移注意事项

由于 Phase 0 → Phase 2 涉及列的删除和重命名，Alembic 自动检测可能不够精确。建议：

1. **Agent 表**：手动编写迁移删除旧列、添加新列
2. **Tool 表**：同上
3. **ModelProvider 表**：`enabled` → `is_enabled` 需要 `ALTER COLUMN RENAME`
4. **新建表**：`llm_models`、`agent_tools`、`agent_knowledge_bases` 可自动生成

### 12.4 Phase 2 完成验证清单

- [ ] `GET /api/agents` 返回 6 个预置 Agent
- [ ] `GET /api/agents/:id` 可查看预置 Agent 详情（含完整 system_prompt）
- [ ] `POST /api/agents` 创建自定义 Agent 成功
- [ ] `PUT /api/agents/:id` 更新自定义 Agent 成功
- [ ] `PUT /api/agents/:id` 修改预置 Agent 返回 403
- [ ] `DELETE /api/agents/:id` 删除自定义 Agent 成功
- [ ] `DELETE /api/agents/:id` 删除预置 Agent 返回 403
- [ ] `POST /api/agents/:id/copy` 复制预置 Agent 成功
- [ ] `GET /api/tools` 返回 7 个预置工具
- [ ] `POST /api/tools` 创建自定义工具成功（含 auth_config 加密）
- [ ] `GET /api/tools/:id` 详情中 auth_config 脱敏
- [ ] `DELETE /api/tools/:id` 有引用时返回引用数（不传 force）
- [ ] `DELETE /api/tools/:id?force=true` 强制删除成功
- [ ] `POST /api/tools/:id/test` 测试调用功能正常
- [ ] `POST /api/models/providers` 添加供应商成功
- [ ] `GET /api/models/providers` 列表 API Key 脱敏
- [ ] `POST /api/models/providers/:id/toggle` 启用/禁用切换
- [ ] `POST /api/models/providers/:id/models` 添加模型
- [ ] `POST /api/models/:id/set-default` 设为默认
- [ ] `GET /api/models/usage` 用量统计
- [ ] Fernet 加密/解密功能正常
- [ ] pytest 全部通过

---

## 附录 A：API 路由总表

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/api/agents` | Agent 列表 | 登录 |
| GET | `/api/agents/:id` | Agent 详情 | 登录 |
| POST | `/api/agents` | 创建自定义 Agent | 登录 |
| PUT | `/api/agents/:id` | 更新自定义 Agent | 登录（仅自己的） |
| DELETE | `/api/agents/:id` | 删除自定义 Agent | 登录（仅自己的） |
| POST | `/api/agents/:id/copy` | 复制预置 Agent | 登录 |
| GET | `/api/tools` | 工具列表 | 登录 |
| GET | `/api/tools/:id` | 工具详情 | 登录 |
| POST | `/api/tools` | 创建自定义工具 | 登录 |
| PUT | `/api/tools/:id` | 更新自定义工具 | 登录（仅自己的） |
| DELETE | `/api/tools/:id` | 删除自定义工具 | 登录（仅自己的） |
| POST | `/api/tools/:id/test` | 测试调用工具 | 登录 |
| GET | `/api/models/providers` | 供应商列表 | 登录 |
| POST | `/api/models/providers` | 添加供应商 | 登录 |
| PUT | `/api/models/providers/:id` | 更新供应商 | 登录（仅自己的） |
| DELETE | `/api/models/providers/:id` | 删除供应商 | 登录（仅自己的） |
| POST | `/api/models/providers/:id/toggle` | 启用/禁用供应商 | 登录（仅自己的） |
| GET | `/api/models/providers/:id/models` | 供应商下模型列表 | 登录（仅自己的） |
| POST | `/api/models/providers/:id/models` | 添加模型 | 登录（仅自己的） |
| PUT | `/api/models/:model_id` | 更新模型配置 | 登录（仅自己的） |
| DELETE | `/api/models/:model_id` | 删除模型 | 登录（仅自己的） |
| POST | `/api/models/:model_id/set-default` | 设为默认模型 | 登录 |
| GET | `/api/models/usage` | 用量统计 | 登录 |

## 附录 B：数据库表关系（Phase 2 新增/修改）

```
Agent (N) ──< AgentTool (N) >── Tool (1)
Agent (N) ──< AgentKnowledgeBase (N) >── KnowledgeBase (1)  [Phase 2 建表，Phase 3 激活]
Agent (N) ──> LLMModel (1)
LLMModel (N) ──> ModelProvider (1)
ModelProvider (1) ──< LLMModel (N)
User (1) ──< ModelProvider (N)
User (1) ──< ModelUsage (N)
```

## 附录 C：常见模型价格参考

| 模型名称 | 输入价格($/M tokens) | 输出价格($/M tokens) |
|----------|---------------------|---------------------|
| gpt-4o | 2.50 | 10.00 |
| gpt-4o-mini | 0.15 | 0.60 |
| gpt-4-turbo | 10.00 | 30.00 |
| gpt-3.5-turbo | 0.50 | 1.50 |
| claude-3-5-sonnet-20241022 | 3.00 | 15.00 |
| claude-3-opus-20240229 | 15.00 | 75.00 |
| claude-3-haiku-20240307 | 0.25 | 1.25 |
| gemini-1.5-pro | 1.25 | 5.00 |
| gemini-1.5-flash | 0.075 | 0.30 |

> 价格随供应商官方调整，以上仅为预填充参考值。用户创建模型时可自定义。

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
