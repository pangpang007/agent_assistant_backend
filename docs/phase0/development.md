---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 4263223131904378_0/project_7661866342080954651-files/Phase0/phase0_backend.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 4263223131904378#1783927337163
    ReservedCode2: ""
---
# 汤圆的代码助手 - Phase 0 后端开发文档

> **目标读者**：Cursor / AI Coding Agent  
> **版本**：Phase 0 v1.0  
> **项目代号**：`tangyuan-backend`  
> **实施计划**：[implementation-plan.md](implementation-plan.md) · **阶段索引**：[README.md](README.md)

---

## 1. 目标

搭建「汤圆的代码助手」后端项目脚手架：完成项目初始化、全部数据库表结构（15 张表）的 SQLAlchemy 模型与 Pydantic Schema 定义、基础中间件（CORS / 请求日志 / 全局异常处理 / 数据库连接池 / Redis 连接）、健康检查接口，以及 Docker Compose 本地开发环境。Phase 0 完成后，项目应能直接启动并通过 `/api/health` 验证所有基础设施可用。

---

## 2. 技术栈

| 层面 | 技术选型 | 版本要求 |
|------|---------|---------|
| 语言 | Python | 3.11+ |
| Web 框架 | FastAPI | 0.110+ |
| ORM | SQLAlchemy (async) | 2.0+ |
| 数据库迁移 | Alembic | 1.13+ |
| 数据库 | PostgreSQL + pgvector 扩展 | 15+ |
| 缓存 / 消息 | Redis | 7+ |
| 数据校验 | Pydantic | v2 |
| 认证 | python-jose（JWT）+ bcrypt | - |
| 配置管理 | pydantic-settings（.env） | - |
| 日志 | structlog（结构化日志） | - |
| 测试 | pytest + httpx（AsyncClient） | - |
| 容器化 | Docker Compose | - |

### 核心依赖清单（requirements.txt / pyproject.toml）

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
sqlalchemy[asyncio]>=2.0.29
asyncpg>=0.29.0
alembic>=1.13.1
pgvector>=0.2.5
pydantic>=2.6.0
pydantic-settings>=2.2.0
python-jose[cryptography]>=3.3.0
bcrypt>=4.1.0
redis[hiredis]>=5.0.0
httpx>=0.27.0
structlog>=24.1.0
python-multipart>=0.0.9
```

---

## 3. 项目目录结构

```
tangyuan-backend/
├── alembic/                     # Alembic 迁移
│   ├── versions/                # 迁移脚本
│   ├── env.py
│   └── script.py.mako
├── alembic.ini                  # Alembic 配置
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI 入口，挂载路由和中间件
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # pydantic-settings 配置类
│   │   ├── database.py          # async engine + session factory
│   │   ├── redis.py             # Redis 连接管理
│   │   ├── security.py          # JWT / bcrypt 工具函数
│   │   ├── exceptions.py        # 自定义异常类
│   │   └── logging.py           # structlog 配置
│   ├── models/                  # SQLAlchemy ORM 模型
│   │   ├── __init__.py          # 导出所有 Base model
│   │   ├── base.py              # Base 类、公共 mixin
│   │   ├── user.py
│   │   ├── agent.py
│   │   ├── tool.py
│   │   ├── knowledge.py         # KnowledgeBase + Document + Chunk
│   │   ├── model_provider.py    # ModelProvider + ModelUsage
│   │   ├── workflow.py          # Workflow + WorkflowVersion
│   │   ├── template.py
│   │   ├── execution.py         # Execution + ExecutionNode + Log
│   │   └── env_variable.py
│   ├── schemas/                 # Pydantic request/response schemas
│   │   ├── __init__.py
│   │   ├── common.py            # 通用 schema（分页、错误响应等）
│   │   ├── user.py
│   │   ├── agent.py
│   │   ├── tool.py
│   │   ├── knowledge.py
│   │   ├── model_provider.py
│   │   ├── workflow.py
│   │   ├── template.py
│   │   ├── execution.py
│   │   └── env_variable.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py            # 总路由聚合
│   │   ├── deps.py              # 依赖注入（get_db, get_current_user 等）
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── health.py        # GET /api/health
│   │   │   ├── users.py         # 用户相关路由（空骨架）
│   │   │   ├── agents.py        # Agent 路由（空骨架）
│   │   │   ├── tools.py         # 工具路由（空骨架）
│   │   │   ├── knowledge.py     # 知识库路由（空骨架）
│   │   │   ├── models.py        # 模型提供商路由（空骨架）
│   │   │   ├── workflows.py     # 工作流路由（空骨架）
│   │   │   ├── templates.py     # 模板路由（空骨架）
│   │   │   ├── executions.py    # 执行记录路由（空骨架）
│   │   │   └── env_vars.py      # 环境变量路由（空骨架）
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── request_log.py       # 请求日志中间件
│   │   └── error_handler.py     # 全局异常处理中间件
│   └── utils/
│       ├── __init__.py
│       └── pagination.py        # 分页工具
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # fixtures: async client, db session
│   ├── test_health.py
│   └── test_models.py
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── .env                         # 本地开发（git-ignored）
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## 4. 数据库模型（完整定义）

### 4.0 公共基类与枚举

#### `app/models/base.py`

```python
import uuid
from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有模型的声明基类"""
    pass


class TimestampMixin:
    """公共时间戳 mixin：created_at + updated_at"""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """UUID 主键 mixin"""
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
```

#### 枚举定义（统一放在各模型文件中或单独 `app/models/enums.py`）

```python
import enum


class MemoryStrategy(str, enum.Enum):
    none = "none"
    window = "window"
    summary = "summary"


class OutputFormat(str, enum.Enum):
    json = "json"
    markdown = "markdown"
    text = "text"


class ToolType(str, enum.Enum):
    builtin = "builtin"
    custom = "custom"


class DocumentStatus(str, enum.Enum):
    processing = "processing"
    ready = "ready"
    failed = "failed"


class ExecutionStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    paused = "paused"
    cancelled = "cancelled"


class NodeStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    skipped = "skipped"
    paused = "paused"


class LogLevel(str, enum.Enum):
    info = "info"
    warn = "warn"
    error = "error"


class EnvVarType(str, enum.Enum):
    string = "string"
    secret = "secret"
```

#### JSON 字段存储说明

- **所有 JSON 字段**统一使用 `sqlalchemy.dialects.postgresql.JSONB` 类型存储，支持 GIN 索引和 JSONPath 查询。
- 在 ORM 模型中，JSON 字段使用 `Mapped[dict | list | None]` 类型注解，配合 SQLAlchemy 的 `JSONB` 列类型自动序列化/反序列化。
- 对于可能为 `null` 的 JSON 字段，使用 `Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)`。

---

### 4.1 User（用户）

#### SQLAlchemy 模型 `app/models/user.py`

```python
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # Relationships
    agents = relationship("Agent", back_populates="user", cascade="all, delete-orphan")
    tools = relationship("Tool", back_populates="user")
    knowledge_bases = relationship("KnowledgeBase", back_populates="user", cascade="all, delete-orphan")
    model_providers = relationship("ModelProvider", back_populates="user", cascade="all, delete-orphan")
    workflows = relationship("Workflow", back_populates="user", cascade="all, delete-orphan")
    env_variables = relationship("EnvVariable", back_populates="user", cascade="all, delete-orphan")
    model_usages = relationship("ModelUsage", back_populates="user")
```

#### 索引策略

| 字段 | 索引类型 | 说明 |
|------|---------|------|
| email | UNIQUE INDEX | 登录唯一标识，高频查询 |

#### Pydantic Schemas `app/schemas/user.py`

```python
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class UserUpdate(BaseModel):
    avatar_url: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    avatar_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

---

### 4.2 Agent（智能体）

#### SQLAlchemy 模型 `app/models/agent.py`

```python
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, Boolean, DateTime, Text, ForeignKey, func
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
    model_provider: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tools: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    knowledge_base_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    memory_strategy: Mapped[MemoryStrategy] = mapped_column(
        nullable=False, default=MemoryStrategy.none, server_default="none"
    )
    output_format: Mapped[OutputFormat] = mapped_column(
        nullable=False, default=OutputFormat.markdown, server_default="markdown"
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
```

#### 索引策略

| 字段 | 索引类型 | 说明 |
|------|---------|------|
| user_id | INDEX | 按用户查询其创建的 Agent |
| name | INDEX | 按名称搜索 |

#### Pydantic Schemas `app/schemas/agent.py`

```python
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    tools: Optional[List[str]] = []
    knowledge_base_ids: Optional[List[str]] = []
    memory_strategy: str = Field(default="none", pattern="^(none|window|summary)$")
    output_format: str = Field(default="markdown", pattern="^(json|markdown|text)$")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=128000)


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    tools: Optional[List[str]] = None
    knowledge_base_ids: Optional[List[str]] = None
    memory_strategy: Optional[str] = Field(None, pattern="^(none|window|summary)$")
    output_format: Optional[str] = Field(None, pattern="^(json|markdown|text)$")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=128000)


class AgentResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    tools: Optional[list] = None
    knowledge_base_ids: Optional[list] = None
    memory_strategy: str
    output_format: str
    temperature: float
    max_tokens: int
    is_preset: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

---

### 4.3 Tool（工具）

#### SQLAlchemy 模型 `app/models/tool.py`

```python
import uuid
from typing import Optional

from sqlalchemy import String, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin
from .enums import ToolType


class Tool(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tools"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[ToolType] = mapped_column(nullable=False, default=ToolType.builtin)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # config 结构示例:
    # {
    #   "openapi_spec": {...},      # OpenAPI 3.0 规范描述
    #   "url": "https://api.xxx",   # 调用端点
    #   "auth": {"type": "bearer", "token": "xxx"}
    # }
    is_preset: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Relationships
    user = relationship("User", back_populates="tools")
```

#### 索引策略

| 字段 | 索引类型 | 说明 |
|------|---------|------|
| user_id | INDEX | 按用户查询工具 |
| name | INDEX | 按名称搜索 |

#### Pydantic Schemas `app/schemas/tool.py`

```python
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


class ToolCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    type: str = Field(default="custom", pattern="^(builtin|custom)$")
    config: Optional[dict[str, Any]] = None


class ToolUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    config: Optional[dict[str, Any]] = None


class ToolResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    name: str
    description: Optional[str] = None
    type: str
    config: Optional[dict] = None
    is_preset: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

---

### 4.4 KnowledgeBase（知识库）

#### SQLAlchemy 模型 `app/models/knowledge.py`

```python
import uuid
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Integer, Text, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin
from .enums import DocumentStatus


class KnowledgeBase(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "knowledge_bases"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False, default="text-embedding-3-small")
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=512, server_default="512")
    chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False, default=50, server_default="50")

    # Relationships
    user = relationship("User", back_populates="knowledge_bases")
    documents = relationship("KnowledgeDocument", back_populates="knowledge_base", cascade="all, delete-orphan")
    chunks = relationship("KnowledgeChunk", back_populates="knowledge_base", cascade="all, delete-orphan")


class KnowledgeDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "knowledge_documents"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[DocumentStatus] = mapped_column(
        nullable=False, default=DocumentStatus.processing, server_default="processing", index=True
    )
    file_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    chunks = relationship("KnowledgeChunk", back_populates="document", cascade="all, delete-orphan")


class KnowledgeChunk(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "knowledge_chunks"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(1536), nullable=True)  # 1536 维向量，用于相似度检索
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="chunks")
    document = relationship("KnowledgeDocument", back_populates="chunks")
```

#### 索引策略

| 表 | 字段 | 索引类型 | 说明 |
|----|------|---------|------|
| knowledge_bases | user_id | INDEX | 按用户查询知识库 |
| knowledge_bases | name | INDEX | 按名称搜索 |
| knowledge_documents | knowledge_base_id | INDEX | 按知识库查文档 |
| knowledge_documents | status | INDEX | 按状态筛选（处理中/完成/失败） |
| knowledge_chunks | knowledge_base_id | INDEX | 按知识库查 chunk |
| knowledge_chunks | document_id | INDEX | 按文档查 chunk |
| knowledge_chunks | embedding | IVFFlat / HNSW | pgvector 向量索引，用于相似性搜索 |

#### 向量索引（Alembic migration 中手动添加）

```python
# 在迁移文件中，KnowledgeChunk 表创建后添加：
from sqlalchemy import text

# HNSW 索引（推荐，构建慢但查询快）
op.execute(
    "CREATE INDEX ix_knowledge_chunks_embedding_hnsw "
    "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops) "
    "WITH (m = 16, ef_construction = 64)"
)
```

#### Pydantic Schemas `app/schemas/knowledge.py`

```python
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ---- KnowledgeBase ----
class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    embedding_model: str = "text-embedding-3-small"
    chunk_size: int = Field(default=512, ge=100, le=10000)
    chunk_overlap: int = Field(default=50, ge=0, le=2000)


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    chunk_size: Optional[int] = Field(None, ge=100, le=10000)
    chunk_overlap: Optional[int] = Field(None, ge=0, le=2000)


class KnowledgeBaseResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: Optional[str] = None
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---- KnowledgeDocument ----
class KnowledgeDocumentResponse(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    filename: str
    file_size: int
    chunk_count: int
    status: str
    file_path: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---- KnowledgeChunk ----
class KnowledgeChunkResponse(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    chunk_index: int
    created_at: datetime

    model_config = {"from_attributes": True}
```

---

### 4.5 ModelProvider（模型提供商）

#### SQLAlchemy 模型 `app/models/model_provider.py`

```python
import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Boolean, Integer, Date, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class ModelProvider(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "model_providers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    api_key_encrypted: Mapped[str] = mapped_column(String(1024), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Relationships
    user = relationship("User", back_populates="model_providers")


class ModelUsage(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "model_usages"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at = mapped_column(
        __import__("sqlalchemy").DateTime(timezone=True),
        server_default=__import__("sqlalchemy").func.now(),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="model_usages")
```

#### 索引策略

| 表 | 字段 | 索引类型 | 说明 |
|----|------|---------|------|
| model_providers | user_id | INDEX | 按用户查提供商 |
| model_providers | provider_name | INDEX | 按提供商名查询 |
| model_usages | user_id | INDEX | 按用户查用量 |
| model_usages | date | INDEX | 按日期范围查用量 |

#### Pydantic Schemas `app/schemas/model_provider.py`

```python
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class ModelProviderCreate(BaseModel):
    provider_name: str = Field(..., min_length=1, max_length=100)
    api_key: str = Field(..., min_length=1)
    base_url: Optional[str] = None
    is_default: bool = False
    enabled: bool = True


class ModelProviderUpdate(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    is_default: Optional[bool] = None
    enabled: Optional[bool] = None


class ModelProviderResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    provider_name: str
    base_url: Optional[str] = None
    is_default: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ModelUsageResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    provider_name: str
    model_name: str
    input_tokens: int
    output_tokens: int
    cost: Decimal
    date: date
    created_at: datetime

    model_config = {"from_attributes": True}
```

---

### 4.6 Workflow（工作流）

#### SQLAlchemy 模型 `app/models/workflow.py`

```python
import uuid
from typing import Optional

from sqlalchemy import String, Integer, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class Workflow(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "workflows"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    nodes_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    edges_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    current_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    is_published_api: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    published_api_key: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, unique=True
    )

    # Relationships
    user = relationship("User", back_populates="workflows")
    versions = relationship("WorkflowVersion", back_populates="workflow", cascade="all, delete-orphan")
    executions = relationship("Execution", back_populates="workflow", cascade="all, delete-orphan")
    template = relationship("Template", back_populates="workflow", uselist=False, cascade="all, delete-orphan")


class WorkflowVersion(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "workflow_versions"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tag: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    nodes_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    edges_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    created_at = mapped_column(
        __import__("sqlalchemy").DateTime(timezone=True),
        server_default=__import__("sqlalchemy").func.now(),
        nullable=False,
    )

    # Relationships
    workflow = relationship("Workflow", back_populates="versions")
```

#### 索引策略

| 表 | 字段 | 索引类型 | 说明 |
|----|------|---------|------|
| workflows | user_id | INDEX | 按用户查工作流 |
| workflows | name | INDEX | 按名称搜索 |
| workflows | published_api_key | UNIQUE | API 调用时查找 |
| workflow_versions | workflow_id | INDEX | 按工作流查版本 |

#### Pydantic Schemas `app/schemas/workflow.py`

```python
import uuid
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field


class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    nodes_json: Optional[List[dict[str, Any]]] = None
    edges_json: Optional[List[dict[str, Any]]] = None


class WorkflowUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    nodes_json: Optional[List[dict[str, Any]]] = None
    edges_json: Optional[List[dict[str, Any]]] = None


class WorkflowResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: Optional[str] = None
    nodes_json: Optional[list] = None
    edges_json: Optional[list] = None
    current_version: int
    is_published_api: bool
    published_api_key: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowVersionResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    version_number: int
    tag: Optional[str] = None
    nodes_json: Optional[list] = None
    edges_json: Optional[list] = None
    created_at: datetime

    model_config = {"from_attributes": True}
```

---

### 4.7 Template（模板）

#### SQLAlchemy 模型 `app/models/template.py`

```python
import uuid
from typing import Optional

from sqlalchemy import String, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin


class Template(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "templates"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    use_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at = mapped_column(
        __import__("sqlalchemy").DateTime(timezone=True),
        server_default=__import__("sqlalchemy").func.now(),
        nullable=False,
    )

    # Relationships
    workflow = relationship("Workflow", back_populates="template")
```

#### 索引策略

| 字段 | 索引类型 | 说明 |
|------|---------|------|
| workflow_id | UNIQUE INDEX | 一个工作流对应一个模板 |
| name | INDEX | 按名称搜索模板 |
| category | INDEX | 按分类筛选模板 |

#### Pydantic Schemas `app/schemas/template.py`

```python
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TemplateCreate(BaseModel):
    workflow_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    category: str = Field(..., min_length=1, max_length=100)
    thumbnail_url: Optional[str] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = None
    thumbnail_url: Optional[str] = None


class TemplateResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    name: str
    description: Optional[str] = None
    category: str
    thumbnail_url: Optional[str] = None
    use_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
```

---

### 4.8 Execution（执行记录）

#### SQLAlchemy 模型 `app/models/execution.py`

```python
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Integer, DateTime, Numeric, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin
from .enums import ExecutionStatus, NodeStatus, LogLevel


class Execution(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "executions"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(
        nullable=False, default=ExecutionStatus.pending, server_default="pending", index=True
    )
    input_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    total_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    workflow = relationship("Workflow", back_populates="executions")
    nodes = relationship("ExecutionNode", back_populates="execution", cascade="all, delete-orphan")
    logs = relationship("Log", back_populates="execution", cascade="all, delete-orphan")


class ExecutionNode(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "execution_nodes"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(100), nullable=False)
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[NodeStatus] = mapped_column(
        nullable=False, default=NodeStatus.pending, server_default="pending"
    )
    input_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    execution = relationship("Execution", back_populates="nodes")


class Log(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "logs"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[LogLevel] = mapped_column(nullable=False, default=LogLevel.info)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    node_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    execution = relationship("Execution", back_populates="logs")
```

#### 索引策略

| 表 | 字段 | 索引类型 | 说明 |
|----|------|---------|------|
| executions | workflow_id | INDEX | 按工作流查执行记录 |
| executions | status | INDEX | 按状态筛选 |
| execution_nodes | execution_id | INDEX | 按执行记录查节点 |
| logs | execution_id | INDEX | 按执行记录查日志 |

#### Pydantic Schemas `app/schemas/execution.py`

```python
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class ExecutionResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    version_number: int
    status: str
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    total_duration_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    total_cost: Optional[Decimal] = None
    started_at: datetime
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ExecutionNodeResponse(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
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


class LogResponse(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    level: str
    message: str
    node_id: Optional[str] = None
    timestamp: datetime

    model_config = {"from_attributes": True}
```

---

### 4.9 EnvVariable（环境变量）

#### SQLAlchemy 模型 `app/models/env_variable.py`

```python
import uuid
from typing import Optional

from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin
from .enums import EnvVarType


class EnvVariable(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "env_variables"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    value_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[EnvVarType] = mapped_column(
        nullable=False, default=EnvVarType.string, server_default="string"
    )

    # Relationships
    user = relationship("User", back_populates="env_variables")
```

#### 索引策略

| 字段 | 索引类型 | 说明 |
|------|---------|------|
| user_id | INDEX | 按用户查环境变量 |
| key | INDEX | 按 key 查询 |

> 注意：建议添加 `(user_id, key)` 复合唯一约束，确保同一用户下 key 不重复。

```python
# 在 Alembic migration 中添加：
op.create_unique_constraint("uq_env_variables_user_key", "env_variables", ["user_id", "key"])
```

#### Pydantic Schemas `app/schemas/env_variable.py`

```python
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class EnvVariableCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=255, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    value: str = Field(..., min_length=1)
    type: str = Field(default="string", pattern="^(string|secret)$")


class EnvVariableUpdate(BaseModel):
    value: Optional[str] = Field(None, min_length=1)
    type: Optional[str] = Field(None, pattern="^(string|secret)$")


class EnvVariableResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    key: str
    type: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
    # 注意：Response 中不暴露 value，防止泄露
```

---

## 5. 基础中间件

### 5.1 CORS 配置 `app/middleware/__init__.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


def setup_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # 从配置读取
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

### 5.2 请求日志中间件 `app/middleware/request_log.py`

```python
import time
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger()


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        await logger.ainfo(
            "http_request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            client_ip=request.client.host if request.client else None,
        )

        response.headers["X-Request-ID"] = request_id
        return response
```

### 5.3 全局异常处理中间件 `app/middleware/error_handler.py`

```python
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.exceptions import AppException

logger = structlog.get_logger()


def setup_error_handlers(app: FastAPI) -> None:

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "请求参数校验失败",
                    "details": [
                        {
                            "field": ".".join(str(loc) for loc in err["loc"]),
                            "message": err["msg"],
                        }
                        for err in exc.errors()
                    ],
                }
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        await logger.aerror("db_integrity_error", error=str(exc.orig))
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "CONFLICT",
                    "message": "数据冲突，资源已存在",
                    "details": [],
                }
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        await logger.aerror("unhandled_exception", error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务器内部错误",
                    "details": [],
                }
            },
        )
```

### 5.4 自定义异常类 `app/core/exceptions.py`

```python
from typing import Optional, Any


class AppException(Exception):
    """应用级基础异常"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[list[Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, resource: str, identifier: str = ""):
        msg = f"{resource}不存在"
        if identifier:
            msg = f"{resource} '{identifier}' 不存在"
        super().__init__(code="NOT_FOUND", message=msg, status_code=404)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "未授权，请先登录"):
        super().__init__(code="UNAUTHORIZED", message=message, status_code=401)


class ForbiddenException(AppException):
    def __init__(self, message: str = "无权限访问此资源"):
        super().__init__(code="FORBIDDEN", message=message, status_code=403)
```

---

## 6. 数据库连接 `app/core/database.py`

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import QueuePool

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=20,               # 连接池常驻连接数
    max_overflow=10,            # 最大溢出连接
    pool_pre_ping=True,         # 自动检测失效连接
    pool_recycle=3600,          # 连接回收时间（秒）
    echo=settings.debug,        # debug 模式打印 SQL
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库 session"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

## 7. Redis 连接 `app/core/redis.py`

```python
import redis.asyncio as aioredis
from app.core.config import settings

redis_client: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    global redis_client
    redis_client = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=50,
    )
    return redis_client


async def close_redis() -> None:
    global redis_client
    if redis_client:
        await redis_client.close()


def get_redis() -> aioredis.Redis:
    if redis_client is None:
        raise RuntimeError("Redis client not initialized")
    return redis_client
```

---

## 8. API 路由骨架

### 8.1 总路由 `app/api/router.py`

```python
from fastapi import APIRouter

from app.api.v1 import (
    health,
    users,
    agents,
    tools,
    knowledge,
    models,
    workflows,
    templates,
    executions,
    env_vars,
)

api_router = APIRouter(prefix="/api")

# Phase 0: 仅实现 health
api_router.include_router(health.router, tags=["Health"])

# Phase 1+ 路由骨架（空 router，后续填充）
api_router.include_router(users.router, prefix="/v1/users", tags=["Users"])
api_router.include_router(agents.router, prefix="/v1/agents", tags=["Agents"])
api_router.include_router(tools.router, prefix="/v1/tools", tags=["Tools"])
api_router.include_router(knowledge.router, prefix="/v1/knowledge", tags=["Knowledge"])
api_router.include_router(models.router, prefix="/v1/models", tags=["Models"])
api_router.include_router(workflows.router, prefix="/v1/workflows", tags=["Workflows"])
api_router.include_router(templates.router, prefix="/v1/templates", tags=["Templates"])
api_router.include_router(executions.router, prefix="/v1/executions", tags=["Executions"])
api_router.include_router(env_vars.router, prefix="/v1/env-vars", tags=["Env Variables"])
```

### 8.2 健康检查 `app/api/v1/health.py`

```python
from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import engine
from app.core.redis import get_redis

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    健康检查接口。
    返回 status、数据库连接状态、Redis 连接状态。
    """
    checks = {}

    # 检查 PostgreSQL
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"

    # 检查 Redis
    try:
        r = get_redis()
        await r.ping()
        checks["redis"] = "connected"
    except Exception as e:
        checks["redis"] = f"error: {str(e)}"

    all_ok = all(v == "connected" for v in checks.values())

    return {
        "status": "healthy" if all_ok else "degraded",
        "version": "0.1.0",
        "checks": checks,
    }
```

### 8.3 空路由模板（以 `app/api/v1/users.py` 为例）

```python
from fastapi import APIRouter

router = APIRouter()

# Phase 1 实现:
# POST   /          - 注册
# GET    /me        - 获取当前用户
# PATCH  /me        - 更新当前用户
# POST   /login     - 登录（返回 JWT）
# POST   /refresh   - 刷新 Token
```

其他空路由文件结构相同，仅声明 `router = APIRouter()` 并注释后续要实现的端点。

---

## 9. 配置管理

### 9.1 `.env.example`

```env
# ---- Application ----
APP_NAME=汤圆的代码助手
APP_ENV=development
DEBUG=true
SECRET_KEY=change-me-to-a-random-64-char-string

# ---- Database ----
DATABASE_URL=postgresql+asyncpg://tangyuan:tangyuan_dev@localhost:5432/tangyuan_db
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# ---- Redis ----
REDIS_URL=redis://localhost:6379/0

# ---- CORS ----
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]

# ---- JWT ----
JWT_SECRET_KEY=change-me-jwt-secret
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ---- Encryption ----
FERNET_KEY=change-me-fernet-key-32-bytes-base64

# ---- Logging ----
LOG_LEVEL=INFO
```

### 9.2 配置类 `app/core/config.py`

```python
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "汤圆的代码助手"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = "change-me"

    # Database
    database_url: str = "postgresql+asyncpg://tangyuan:tangyuan_dev@localhost:5432/tangyuan_db"
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # CORS
    cors_origins: List[str] = ["http://localhost:3000"]

    # JWT
    jwt_secret_key: str = "change-me-jwt-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Encryption
    fernet_key: str = "change-me-fernet-key"

    # Logging
    log_level: str = "INFO"


settings = Settings()
```

---

## 10. 错误响应格式

所有 API 错误统一返回以下 JSON 结构：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "描述信息",
    "details": [
      {
        "field": "email",
        "message": "invalid email format"
      }
    ]
  }
}
```

### 错误码定义

| HTTP Status | code | 说明 |
|-------------|------|------|
| 400 | VALIDATION_ERROR | 请求参数校验失败 |
| 401 | UNAUTHORIZED | 未认证 / Token 过期 |
| 403 | FORBIDDEN | 无权限 |
| 404 | NOT_FOUND | 资源不存在 |
| 409 | CONFLICT | 数据冲突（唯一约束违反） |
| 422 | VALIDATION_ERROR | FastAPI 自动校验失败 |
| 429 | RATE_LIMITED | 请求频率超限 |
| 500 | INTERNAL_ERROR | 服务器内部错误 |

---

## 11. 启动与部署

### 11.1 本地开发启动

```bash
# 1. 克隆项目
git clone <repo-url> && cd tangyuan-backend

# 2. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 复制环境配置
cp .env.example .env
# 编辑 .env 填写实际配置

# 5. 启动 Docker 服务（PostgreSQL + Redis）
docker compose up -d db redis

# 6. 运行数据库迁移
alembic upgrade head

# 7. 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 11.2 Docker Compose `docker-compose.yml`

```yaml
version: "3.9"

services:
  db:
    image: pgvector/pgvector:pg15
    container_name: tangyuan-db
    environment:
      POSTGRES_USER: tangyuan
      POSTGRES_PASSWORD: tangyuan_dev
      POSTGRES_DB: tangyuan_db
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tangyuan -d tangyuan_db"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: tangyuan-redis
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  api:
    build: .
    container_name: tangyuan-api
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - .:/app
    command: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

volumes:
  pgdata:
  redisdata:
```

### 11.3 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 11.4 Alembic 初始化

```bash
# 初始化 Alembic
alembic init alembic

# 修改 alembic.ini 中 sqlalchemy.url 为：
# sqlalchemy.url = postgresql+asyncpg://tangyuan:tangyuan_dev@localhost:5432/tangyuan_db

# 修改 alembic/env.py（关键部分）
```

#### `alembic/env.py` 关键配置

```python
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 导入所有模型，确保 Base.metadata 包含所有表
from app.models.base import Base
from app.models import (  # noqa: F401
    user, agent, tool, knowledge, model_provider,
    workflow, template, execution, env_variable,
)
from app.core.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

#### 首次迁移

```bash
# 生成初始迁移
alembic revision --autogenerate -m "initial_schema"

# 执行迁移
alembic upgrade head
```

---

## 12. 应用入口 `app/main.py`

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import structlog

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.redis import init_redis, close_redis
from app.middleware.request_log import RequestLogMiddleware
from app.middleware.error_handler import setup_error_handlers
from app.api.router import api_router

# 初始化结构化日志
setup_logging()

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("starting_application", app_name=settings.app_name)
    await init_redis()
    yield
    await close_redis()
    logger.info("stopping_application")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# 挂载中间件
app.add_middleware(RequestLogMiddleware)
setup_error_handlers(app)

# 挂载路由
app.include_router(api_router)
```

---

## 13. structlog 配置 `app/core/logging.py`

```python
import logging
import structlog
from app.core.config import settings


def setup_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if settings.debug
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

---

## 14. 安全工具 `app/core/security.py`

```python
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
import bcrypt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        return None
```

---

## 15. 依赖注入 `app/api/deps.py`

```python
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """解析 JWT 并返回当前用户"""
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的 Token",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="无效 Token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


# 类型别名，方便在路由中使用
CurrentUser = Annotated[User, Depends(get_current_user)]
DBSession = Annotated[AsyncSession, Depends(get_db)]
```

---

## 16. 通用 Schema `app/schemas/common.py`

```python
from typing import Generic, TypeVar, Optional, List
from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """通用分页响应"""
    items: List[T]
    total: int
    page: int
    page_size: int
    has_next: bool


class ErrorResponse(BaseModel):
    """统一错误响应"""
    code: str
    message: str
    details: Optional[list] = None


class ErrorResponseWrapper(BaseModel):
    """错误响应包装"""
    error: ErrorResponse
```

---

## 17. 测试配置 `tests/conftest.py`

```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "checks" in data
```

---

## 18. 数据库表关系总览

```
User (1) ──< Agent (N)
User (1) ──< Tool (N)
User (1) ──< KnowledgeBase (N)
User (1) ──< ModelProvider (N)
User (1) ──< ModelUsage (N)
User (1) ──< Workflow (N)
User (1) ──< EnvVariable (N)

KnowledgeBase (1) ──< KnowledgeDocument (N)
KnowledgeBase (1) ──< KnowledgeChunk (N)
KnowledgeDocument (1) ──< KnowledgeChunk (N)

Workflow (1) ──< WorkflowVersion (N)
Workflow (1) ──< Execution (N)
Workflow (1) ── (0..1) Template

Execution (1) ──< ExecutionNode (N)
Execution (1) ──< Log (N)
```

---

## 19. 给 Cursor 的额外说明

### 代码生成优先级

1. **先创建所有基础设施文件**：`app/main.py`、`app/core/config.py`、`app/core/database.py`、`app/core/redis.py`、`app/core/logging.py`、`app/core/security.py`、`app/core/exceptions.py`
2. **再创建所有模型文件**：`app/models/base.py` 和 `app/models/enums.py` 优先，然后是各业务模型
3. **再创建所有 schema 文件**
4. **再创建中间件和路由**
5. **最后配置 Alembic 并生成首次迁移**

### 关键约束

- **所有主键**使用 UUID v4，由 Python 端 `uuid.uuid4()` 生成（非数据库端）
- **所有时间戳**使用 `DateTime(timezone=True)` 存储 UTC 时间
- **所有枚举**使用 Python `str, enum.Enum` 定义，数据库存储为字符串值
- **JSON 字段**使用 PostgreSQL `JSONB` 类型
- **向量字段**使用 `pgvector` 扩展的 `Vector(1536)` 类型
- **外键**统一使用 `ondelete="CASCADE"`（除 Tool.user_id 使用 `SET NULL`）
- **密码**使用 bcrypt 加密存储，API 响应中**绝不返回** `password_hash`
- **API Key**（ModelProvider）使用 Fernet 对称加密存储
- **环境变量值**使用 Fernet 加密存储，API 响应中**绝不返回**加密值
- **Pydantic Schema** 中 `Response` 模型必须设置 `model_config = {"from_attributes": True}`
- **每个模型文件**必须确保对应的 `Base.metadata` 注册了表

### 命名规范

- 数据库表名：复数下划线（`users`、`knowledge_bases`、`execution_nodes`）
- Python 类名：PascalCase（`User`、`KnowledgeBase`、`ExecutionNode`）
- 文件名：下划线（`model_provider.py`、`env_variable.py`）
- API 路径：复数名词（`/api/v1/agents`、`/api/v1/workflows`）

### 验证清单（Phase 0 完成标准）

- [ ] `uvicorn app.main:app --reload` 能正常启动
- [ ] `GET /api/health` 返回 `{"status": "healthy", ...}`
- [ ] `docker compose up -d` 能启动 PostgreSQL + Redis
- [ ] `alembic upgrade head` 能创建所有 15 张表
- [ ] `pgvector` 扩展已启用，`knowledge_chunks.embedding` 列类型为 `vector(1536)`
- [ ] structlog 输出结构化 JSON 日志
- [ ] CORS 中间件正常工作
- [ ] 请求日志记录 method/path/status/duration
- [ ] 全局异常返回统一的 `{"error": {...}}` 格式
- [ ] pytest 能通过 `tests/test_health.py`

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
