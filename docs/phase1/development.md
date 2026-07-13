---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 4263223131904378_0/project_7661866342080954651-files/Phase1/phase1_backend.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 4263223131904378#1783930205525
    ReservedCode2: ""
---
# 汤圆的代码助手 - Phase 1 后端开发文档：用户系统

> **目标读者**：Cursor / AI Coding Agent  
> **版本**：Phase 1 v1.0  
> **项目代号**：`tangyuan-backend`  
> **前置条件**：Phase 0 已完成（FastAPI 脚手架 + 全部数据库模型 + 中间件 + 健康检查）

---

## 1. 目标

在 Phase 0 基础上实现完整的用户系统，包括：

- **注册**：支持个人注册和团队注册两种模式
- **登录**：邮箱 + 密码验证，返回 JWT access_token + refresh_token
- **Token 刷新**：用 refresh_token 换取新的 access_token
- **登出**：基于 Redis 的 token 黑名单机制
- **个人资料管理**：查看/修改个人信息、修改密码
- **团队管理**：创建团队、邀请码加入、成员管理、删除团队

Phase 1 完成后，用户应能完成注册→登录→创建/加入团队→管理团队的完整流程。

---

## 2. Phase 0 模型变更（数据库迁移）

### 2.1 User 模型扩展

Phase 0 的 User 模型仅包含 `email, password_hash, avatar_url`。Phase 1 需要新增以下字段：

```python
# app/models/user.py — Phase 1 变更后的完整模型

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True
    )
    username: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # Phase 1 新增字段
    account_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="personal", server_default="personal", index=True
    )
    # account_type 取值: "personal" | "team"
    # - personal: 个人账号
    # - team: 团队账号（即该用户是某个团队的 owner，且以团队身份使用）

    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # team_id 为 NULL 表示纯个人用户，未加入任何团队
    # team_id 有值且 account_type="team" 表示该用户是该团队的 owner
    # team_id 有值且 account_type="personal" 表示该用户加入了某个团队（作为 member）

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Relationships
    owned_team = relationship(
        "Team",
        back_populates="owner",
        foreign_keys="Team.owner_id",
        uselist=False,
        cascade="all, delete-orphan",
    )
    agents = relationship("Agent", back_populates="user", cascade="all, delete-orphan")
    tools = relationship("Tool", back_populates="user")
    knowledge_bases = relationship("KnowledgeBase", back_populates="user", cascade="all, delete-orphan")
    model_providers = relationship("ModelProvider", back_populates="user", cascade="all, delete-orphan")
    workflows = relationship("Workflow", back_populates="user", cascade="all, delete-orphan")
    env_variables = relationship("EnvVariable", back_populates="user", cascade="all, delete-orphan")
    model_usages = relationship("ModelUsage", back_populates="user")
```

### 2.2 Team 模型新增

```python
# app/models/team.py — Phase 1 新增文件

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class Team(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,   # 一个用户只能拥有一个团队
        index=True,
    )

    invite_code: Mapped[str] = mapped_column(
        String(6), unique=True, nullable=False, index=True
    )
    # 6 位大写字母+数字组成的邀请码，用于团队成员加入

    # Relationships
    owner = relationship("User", back_populates="owned_team", foreign_keys=[owner_id])
    members = relationship(
        "User",
        back_populates="team",
        foreign_keys="User.team_id",
        lazy="selectin",
    )
```

### 2.3 User 模型新增 team relationship

在 User 模型中新增：

```python
    # Phase 1 新增
    team = relationship(
        "Team",
        back_populates="members",
        foreign_keys="User.team_id",
        lazy="selectin",
    )
```

### 2.4 枚举扩展

在 `app/models/enums.py` 中新增：

```python
class AccountType(str, enum.Enum):
    personal = "personal"
    team = "team"
```

### 2.5 Alembic 迁移

Phase 1 需要生成一次新的数据库迁移：

```bash
alembic revision --autogenerate -m "phase1_user_system"
alembic upgrade head
```

迁移内容：
1. `users` 表新增列：`username VARCHAR(100) NOT NULL DEFAULT ''`（需回填）
2. `users` 表新增列：`account_type VARCHAR(20) NOT NULL DEFAULT 'personal'`
3. `users` 表新增列：`team_id UUID NULL`
4. `users` 表新增列：`is_active BOOLEAN NOT NULL DEFAULT true`
5. 新建 `teams` 表
6. 添加外键约束和索引

**注意**：`username` 字段设为 `NOT NULL`，迁移时需要给已有记录设置默认值（如取 email 的 `@` 前部分）。

---

## 3. 配置变更

### 3.1 `.env` 新增配置项

```env
# ---- Phase 1: JWT Token ----
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# ---- Phase 1: Password ----
BCRYPT_ROUNDS=12

# ---- Phase 1: Team ----
TEAM_MAX_MEMBERS=50
INVITE_CODE_LENGTH=6
```

### 3.2 `app/core/config.py` 新增字段

```python
class Settings(BaseSettings):
    # ... Phase 0 已有字段 ...

    # Phase 1: JWT
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # Phase 1: Password
    bcrypt_rounds: int = 12

    # Phase 1: Team
    team_max_members: int = 50
    invite_code_length: int = 6
```

---

## 4. 目录结构变更（Phase 1 新增/修改的文件）

```
app/
├── core/
│   ├── security.py          # 【修改】新增密码策略校验、邀请码生成、token 黑名单操作
│   └── config.py            # 【修改】新增 Phase 1 配置字段
├── models/
│   ├── user.py              # 【修改】扩展 User 模型
│   ├── team.py              # 【新增】Team 模型
│   └── enums.py             # 【修改】新增 AccountType 枚举
├── schemas/
│   ├── auth.py              # 【新增】注册/登录请求/响应 Schema
│   ├── user.py              # 【修改】扩展用户相关 Schema
│   └── team.py              # 【新增】团队相关 Schema
├── services/
│   ├── __init__.py          # 【新增】
│   ├── auth_service.py      # 【新增】认证业务逻辑
│   ├── user_service.py      # 【新增】用户业务逻辑
│   └── team_service.py      # 【新增】团队业务逻辑
├── api/
│   ├── deps.py              # 【修改】扩展权限依赖
│   └── v1/
│       ├── auth.py          # 【新增】认证路由（register/login/refresh/logout）
│       ├── users.py         # 【修改】从空骨架实现用户路由
│       └── teams.py         # 【新增】团队管理路由
└── middleware/
    └── ...（Phase 0 不变）
```

---

## 5. API 完整规格

### 5.0 通用约定

#### 成功响应包装

所有成功响应统一使用以下格式：

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

其中 `data` 字段为具体的业务数据。列表接口 `data` 中额外包含分页信息。

#### 认证方式

除 `/api/auth/register` 和 `/api/auth/login` 外，所有接口都需要在请求头中携带有效的 access_token：

```
Authorization: Bearer <access_token>
```

#### 角色说明

| 角色 | account_type | team_id | 说明 |
|------|-------------|---------|------|
| 个人用户 | personal | NULL | 未加入任何团队 |
| 团队成员 | personal | 有值 | 已加入某团队，但非 owner |
| 团队 owner | team | 有值 | 某团队的所有者 |

---

### 5.1 注册接口

#### `POST /api/auth/register`

**描述**：用户注册，支持个人注册和团队注册。

**权限**：公开接口，无需登录。

**请求体 Schema**：

```python
# app/schemas/auth.py

from pydantic import BaseModel, EmailStr, Field, field_validator
import re


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    account_type: str = Field(default="personal", pattern="^(personal|team)$")
    team_name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r'^[\w\u4e00-\u9fff\-]+$', v):
            raise ValueError("用户名仅支持中英文、数字、下划线和短横线")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("用户名不能以短横线开头或结尾")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r'[A-Z]', v):
            raise ValueError("密码必须包含至少一个大写字母")
        if not re.search(r'[a-z]', v):
            raise ValueError("密码必须包含至少一个小写字母")
        if not re.search(r'[0-9]', v):
            raise ValueError("密码必须包含至少一个数字")
        return v

    @field_validator("team_name")
    @classmethod
    def validate_team_name(cls, v, info):
        account_type = info.data.get("account_type")
        if account_type == "team" and not v:
            raise ValueError("团队注册时必须提供 team_name")
        return v


class RegisterResponse(BaseModel):
    user: "UserResponse"
    team: "TeamResponse | None" = None
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
```

**业务逻辑（逐步）**：

1. 校验请求体（Pydantic 自动完成）
2. 检查 `account_type == "team"` 时 `team_name` 不能为空
3. 查询数据库，检查 `email` 是否已存在
   - 若存在 → 抛出 `409 CONFLICT`，错误码 `EMAIL_ALREADY_REGISTERED`
4. 使用 bcrypt 对密码进行 hash（使用 `settings.bcrypt_rounds` 轮次）
5. 生成 `username`，检查是否重复
   - 若重复 → 抛出 `409 CONFLICT`，错误码 `USERNAME_ALREADY_TAKEN`
6. **个人注册**（`account_type == "personal"`）：
   - 创建 User 记录：`account_type="personal"`, `team_id=None`
   - `team` 返回 `null`
7. **团队注册**（`account_type == "team"`）：
   - 生成 6 位邀请码（大写字母 + 数字）
   - 创建 User 记录：`account_type="team"`, `team_id` 暂为 `None`
   - 创建 Team 记录：`name=team_name`, `owner_id=user.id`, `invite_code=生成的邀请码`
   - 更新 User 记录的 `team_id = team.id`
   - `team` 返回创建的 Team 信息
8. 生成 `access_token` 和 `refresh_token`
9. 返回完整注册响应

**响应体 Schema**：

```python
# app/schemas/user.py

class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    avatar_url: str | None = None
    account_type: str
    team_id: uuid.UUID | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# app/schemas/team.py

class TeamResponse(BaseModel):
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    invite_code: str
    member_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 409 | `EMAIL_ALREADY_REGISTERED` | 邮箱已被注册 |
| 409 | `USERNAME_ALREADY_TAKEN` | 用户名已被占用 |
| 422 | `VALIDATION_ERROR` | 参数校验失败（密码强度不够、邮箱格式错误、团队注册未提供 team_name） |

---

### 5.2 登录接口

#### `POST /api/auth/login`

**描述**：用户登录，验证邮箱和密码，返回 JWT token。

**权限**：公开接口，无需登录。

**请求体 Schema**：

```python
# app/schemas/auth.py

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
```

**业务逻辑（逐步）**：

1. 根据 `email` 查询 User 记录
   - 若不存在 → 抛出 `401 UNAUTHORIZED`，错误码 `INVALID_CREDENTIALS`（注意：不要区分"用户不存在"和"密码错误"，防止枚举攻击）
2. 检查 `user.is_active`
   - 若为 `False` → 抛出 `403 FORBIDDEN`，错误码 `ACCOUNT_DISABLED`
3. 使用 `bcrypt.checkpw()` 验证密码
   - 若不匹配 → 抛出 `401 UNAUTHORIZED`，错误码 `INVALID_CREDENTIALS`
4. 生成 JWT tokens：
   - `access_token` payload: `{ sub: user.id, email: user.email, account_type: user.account_type, team_id: user.team_id, type: "access", exp: now + 15min }`
   - `refresh_token` payload: `{ sub: user.id, email: user.email, account_type: user.account_type, team_id: user.team_id, type: "refresh", exp: now + 30days }`
5. 返回登录响应

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 401 | `INVALID_CREDENTIALS` | 邮箱或密码错误 |
| 403 | `ACCOUNT_DISABLED` | 账号已被禁用 |
| 422 | `VALIDATION_ERROR` | 参数校验失败 |

---

### 5.3 Token 刷新接口

#### `POST /api/auth/refresh`

**描述**：用 refresh_token 换取新的 access_token。

**权限**：需要携带有效的 refresh_token。

**请求头**：

```
Authorization: Bearer <refresh_token>
```

**请求体**：无（从 Authorization header 中获取 refresh_token）

**请求体 Schema**（可选，也支持 body 传参）：

```python
# app/schemas/auth.py

class RefreshRequest(BaseModel):
    refresh_token: str
```

> 实现建议：同时支持 Authorization header 和 body 两种方式。优先从 body 读取，若 body 为空则从 header 读取。

**业务逻辑（逐步）**：

1. 从请求中获取 `refresh_token`
2. 使用 `decode_token()` 解码 token
   - 若解码失败 → 抛出 `401 UNAUTHORIZED`，错误码 `INVALID_TOKEN`
3. 检查 `payload["type"] == "refresh"`
   - 若不是 → 抛出 `401 UNAUTHORIZED`，错误码 `INVALID_TOKEN_TYPE`
4. 检查 Redis token 黑名单中是否存在该 token
   - 若存在 → 抛出 `401 UNAUTHORIZED`，错误码 `TOKEN_REVOKED`
5. 根据 `payload["sub"]` 查询用户，确认用户仍存在且 `is_active=True`
   - 若不存在或已禁用 → 抛出 `401 UNAUTHORIZED`，错误码 `USER_INACTIVE`
6. 生成新的 `access_token`（使用最新的用户信息）
7. 返回新 token

**响应体 Schema**：

```python
# app/schemas/auth.py

class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒数，如 900（15 分钟）
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 401 | `INVALID_TOKEN` | Token 无效或已过期 |
| 401 | `INVALID_TOKEN_TYPE` | Token 类型不正确（需要 refresh_token） |
| 401 | `TOKEN_REVOKED` | Token 已被撤销（在黑名单中） |
| 401 | `USER_INACTIVE` | 用户已不存在或已被禁用 |

---

### 5.4 登出接口

#### `POST /api/auth/logout`

**描述**：用户登出，将当前 access_token 加入 Redis 黑名单。

**权限**：需要登录。

**请求体**：无

**业务逻辑（逐步）**：

1. 从请求头获取当前 `access_token`
2. 解码 token 获取 `exp`（过期时间）
3. 计算 token 剩余有效时间：`ttl = exp - now`
4. 将 token 写入 Redis，key 为 `token_blacklist:{token_jti_or_token_hash}`，value 为 `"revoked"`，TTL 为 token 剩余有效时间
   - 使用 token 的 SHA256 hash 作为 key 的一部分，避免 key 过长
5. 返回成功响应

**响应体 Schema**：

```python
# app/schemas/auth.py

class LogoutResponse(BaseModel):
    message: str = "登出成功"
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 401 | `UNAUTHORIZED` | 未登录或 token 已过期 |

---

### 5.5 获取当前用户信息

#### `GET /api/users/me`

**描述**：获取当前登录用户的完整信息。

**权限**：需要登录。

**请求体**：无

**业务逻辑（逐步）**：

1. 从 `get_current_user` 依赖获取当前用户
2. 如果用户有关联的 team（`team_id` 不为空），额外查询 team 信息
3. 返回用户信息（包含团队信息摘要）

**响应体 Schema**：

```python
# app/schemas/user.py

class UserProfileResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    avatar_url: str | None = None
    account_type: str
    team_id: uuid.UUID | None = None
    team: TeamResponse | None = None  # 关联的团队信息（如有）
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 401 | `UNAUTHORIZED` | 未登录 |

---

### 5.6 更新用户信息

#### `PATCH /api/users/me`

**描述**：更新当前用户的用户名。

**权限**：需要登录。

**请求体 Schema**：

```python
# app/schemas/user.py

class UserUpdateRequest(BaseModel):
    username: str | None = Field(default=None, min_length=2, max_length=100)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.match(r'^[\w\u4e00-\u9fff\-]+$', v):
            raise ValueError("用户名仅支持中英文、数字、下划线和短横线")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("用户名不能以短横线开头或结尾")
        return v
```

**业务逻辑（逐步）**：

1. 获取当前用户
2. 检查请求体中是否有需要更新的字段（至少需要一个字段）
   - 若所有字段均为 `None` → 抛出 `400 BAD_REQUEST`，错误码 `NO_FIELDS_TO_UPDATE`
3. 若更新 `username`：
   - 查询是否有其他用户使用了该 `username`
   - 若重复 → 抛出 `409 CONFLICT`，错误码 `USERNAME_ALREADY_TAKEN`
   - 更新用户的 `username`
4. 提交数据库事务
5. 返回更新后的用户信息

**响应体 Schema**：同 `UserProfileResponse`

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 400 | `NO_FIELDS_TO_UPDATE` | 未提供任何需要更新的字段 |
| 409 | `USERNAME_ALREADY_TAKEN` | 用户名已被占用 |
| 401 | `UNAUTHORIZED` | 未登录 |

---

### 5.7 修改密码

#### `POST /api/users/me/change-password`

**描述**：修改当前用户的密码，需要验证旧密码。

**权限**：需要登录。

**请求体 Schema**：

```python
# app/schemas/auth.py

class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if not re.search(r'[A-Z]', v):
            raise ValueError("密码必须包含至少一个大写字母")
        if not re.search(r'[a-z]', v):
            raise ValueError("密码必须包含至少一个小写字母")
        if not re.search(r'[0-9]', v):
            raise ValueError("密码必须包含至少一个数字")
        return v
```

**业务逻辑（逐步）**：

1. 获取当前用户
2. 使用 `bcrypt.checkpw()` 验证 `old_password` 与当前用户的 `password_hash`
   - 若不匹配 → 抛出 `400 BAD_REQUEST`，错误码 `INVALID_OLD_PASSWORD`
3. 检查 `new_password` 是否与 `old_password` 相同
   - 若相同 → 抛出 `400 BAD_REQUEST`，错误码 `SAME_PASSWORD`
4. 对新密码进行 bcrypt hash
5. 更新用户的 `password_hash`
6. 提交数据库事务
7. **可选**：将当前 access_token 加入黑名单（强制重新登录）
8. 返回成功响应

**响应体 Schema**：

```python
class ChangePasswordResponse(BaseModel):
    message: str = "密码修改成功"
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 400 | `INVALID_OLD_PASSWORD` | 旧密码不正确 |
| 400 | `SAME_PASSWORD` | 新密码不能与旧密码相同 |
| 422 | `VALIDATION_ERROR` | 新密码强度不够 |
| 401 | `UNAUTHORIZED` | 未登录 |

---

### 5.8 创建团队

#### `POST /api/teams`

**描述**：个人用户创建团队。创建后该用户变为团队 owner。

**权限**：需要登录。当前用户必须是 `account_type=personal` 且 `team_id=NULL`（即未加入任何团队）。

**请求体 Schema**：

```python
# app/schemas/team.py

class TeamCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
```

**业务逻辑（逐步）**：

1. 获取当前用户
2. 检查当前用户的 `account_type`
   - 若已经是 `"team"` → 抛出 `409 CONFLICT`，错误码 `ALREADY_HAS_TEAM`（该用户已经拥有团队）
3. 检查当前用户的 `team_id`
   - 若 `team_id` 不为 `None` → 抛出 `409 CONFLICT`，错误码 `ALREADY_IN_TEAM`（该用户已加入其他团队）
4. 生成 6 位邀请码
5. 创建 Team 记录：`name=request.name`, `owner_id=current_user.id`, `invite_code=邀请码`
6. 更新当前用户：`account_type="team"`, `team_id=team.id`
7. 返回创建的团队信息

**响应体 Schema**：

```python
class TeamCreateResponse(BaseModel):
    team: TeamResponse
    user: UserResponse
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 409 | `ALREADY_HAS_TEAM` | 当前用户已经拥有一个团队 |
| 409 | `ALREADY_IN_TEAM` | 当前用户已加入其他团队，请先退出 |
| 401 | `UNAUTHORIZED` | 未登录 |

---

### 5.9 加入团队

#### `POST /api/teams/join`

**描述**：通过邀请码加入团队。

**权限**：需要登录。当前用户必须是 `account_type=personal` 且 `team_id=NULL`。

**请求体 Schema**：

```python
# app/schemas/team.py

class JoinTeamRequest(BaseModel):
    invite_code: str = Field(..., min_length=6, max_length=6)
```

**业务逻辑（逐步）**：

1. 获取当前用户
2. 检查当前用户是否已属于某个团队
   - 若 `account_type == "team"` → 抛出 `409 CONFLICT`，错误码 `ALREADY_HAS_TEAM`
   - 若 `team_id` 不为 `None` → 抛出 `409 CONFLICT`，错误码 `ALREADY_IN_TEAM`
3. 将 `invite_code` 转为大写
4. 根据 `invite_code` 查询 Team 记录
   - 若不存在 → 抛出 `404 NOT_FOUND`，错误码 `INVALID_INVITE_CODE`
5. 查询该团队当前成员数（`users` 表中 `team_id=team.id` 的记录数）
   - 若成员数 >= `settings.team_max_members` → 抛出 `400 BAD_REQUEST`，错误码 `TEAM_FULL`
6. 更新当前用户：`team_id=team.id`（`account_type` 保持 `personal`）
7. 返回团队信息

**响应体 Schema**：

```python
class JoinTeamResponse(BaseModel):
    team: TeamResponse
    user: UserResponse
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 409 | `ALREADY_HAS_TEAM` | 当前用户已拥有团队 |
| 409 | `ALREADY_IN_TEAM` | 当前用户已在其他团队中 |
| 404 | `INVALID_INVITE_CODE` | 邀请码无效 |
| 400 | `TEAM_FULL` | 团队人数已达上限 |
| 401 | `UNAUTHORIZED` | 未登录 |

---

### 5.10 获取团队成员列表

#### `GET /api/teams/members`

**描述**：获取当前用户所在团队的所有成员列表。仅团队 owner 可操作。

**权限**：需要登录 + owner 权限。

**请求参数**：无

**业务逻辑（逐步）**：

1. 获取当前用户
2. 检查当前用户是否为团队 owner（调用 `require_owner` 依赖）
   - 若不是 → 抛出 `403 FORBIDDEN`，错误码 `OWNER_ONLY`
3. 查询当前用户关联的 Team 记录
4. 查询 `users` 表中 `team_id=team.id` 的所有用户
5. 组装成员列表，标记每个成员的角色（owner/member）
6. 返回成员列表

**响应体 Schema**：

```python
# app/schemas/team.py

class TeamMemberResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    avatar_url: str | None = None
    account_type: str  # "personal"（成员）或 "team"（owner）
    role: str  # "owner" 或 "member"
    joined_at: datetime  # 即 user.updated_at（team_id 更新的时间）

    model_config = {"from_attributes": True}


class TeamMembersResponse(BaseModel):
    team_id: uuid.UUID
    team_name: str
    members: list[TeamMemberResponse]
    total: int
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 403 | `OWNER_ONLY` | 仅团队 owner 可操作 |
| 403 | `NOT_IN_TEAM` | 当前用户不属于任何团队 |
| 401 | `UNAUTHORIZED` | 未登录 |

---

### 5.11 移除团队成员

#### `DELETE /api/teams/members/{user_id}`

**描述**：从团队中移除指定成员。仅团队 owner 可操作。不可移除自己。

**权限**：需要登录 + owner 权限。

**路径参数**：
- `user_id`: UUID，要移除的用户 ID

**请求体**：无

**业务逻辑（逐步）**：

1. 获取当前用户（owner）
2. 检查 `require_owner` 权限
3. 检查 `user_id` 是否等于当前用户 ID
   - 若是 → 抛出 `400 BAD_REQUEST`，错误码 `CANNOT_REMOVE_SELF`（owner 不能移除自己，需要用删除团队接口）
4. 根据 `user_id` 查询目标用户
   - 若不存在 → 抛出 `404 NOT_FOUND`，错误码 `USER_NOT_FOUND`
5. 检查目标用户的 `team_id` 是否等于当前团队 ID
   - 若不是 → 抛出 `400 BAD_REQUEST`，错误码 `USER_NOT_IN_TEAM`
6. 将目标用户的 `team_id` 设为 `None`，`account_type` 保持 `"personal"`
7. 提交事务
8. 返回成功响应

**响应体 Schema**：

```python
class RemoveMemberResponse(BaseModel):
    message: str = "成员已移除"
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 403 | `OWNER_ONLY` | 仅团队 owner 可操作 |
| 400 | `CANNOT_REMOVE_SELF` | 不能移除自己 |
| 404 | `USER_NOT_FOUND` | 目标用户不存在 |
| 400 | `USER_NOT_IN_TEAM` | 目标用户不属于当前团队 |
| 401 | `UNAUTHORIZED` | 未登录 |

---

### 5.12 重置邀请码

#### `POST /api/teams/invite-code/reset`

**描述**：重置团队邀请码。仅团队 owner 可操作。

**权限**：需要登录 + owner 权限。

**请求体**：无

**业务逻辑（逐步）**：

1. 获取当前用户（owner）
2. 检查 `require_owner` 权限
3. 查询当前用户关联的 Team 记录
4. 生成新的 6 位邀请码
5. 检查新邀请码是否与数据库中已有的重复（极小概率，但需处理）
   - 若重复 → 重新生成（最多重试 3 次）
6. 更新 Team 的 `invite_code`
7. 提交事务
8. 返回新的邀请码

**响应体 Schema**：

```python
class ResetInviteCodeResponse(BaseModel):
    invite_code: str
    message: str = "邀请码已重置"
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 403 | `OWNER_ONLY` | 仅团队 owner 可操作 |
| 403 | `NOT_IN_TEAM` | 当前用户不属于任何团队 |
| 401 | `UNAUTHORIZED` | 未登录 |

---

### 5.13 删除团队

#### `DELETE /api/teams`

**描述**：删除团队。仅团队 owner 可操作。删除后团队所有成员的 `team_id` 回退为 `None`，`account_type` 回退为 `personal`。

**权限**：需要登录 + owner 权限。

**请求体**：无

**业务逻辑（逐步）**：

1. 获取当前用户（owner）
2. 检查 `require_owner` 权限
3. 查询当前用户关联的 Team 记录
4. 查询该团队下所有成员（`team_id=team.id` 且 `id != owner.id`）
5. **批量更新**所有成员：
   - `team_id = None`
   - `account_type` 保持 `"personal"`（成员本来就是 personal）
6. 删除 Team 记录
7. 更新 owner 用户：
   - `team_id = None`
   - `account_type = "personal"`
8. 提交事务
9. 返回成功响应

**响应体 Schema**：

```python
class DeleteTeamResponse(BaseModel):
    message: str = "团队已删除"
    affected_members: int  # 受影响的成员数量
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 403 | `OWNER_ONLY` | 仅团队 owner 可操作 |
| 403 | `NOT_IN_TEAM` | 当前用户不属于任何团队 |
| 401 | `UNAUTHORIZED` | 未登录 |

---

## 6. 安全模块详细设计

### 6.1 密码策略

```python
# app/core/security.py — Phase 1 扩展

import bcrypt
import re
from app.core.config import settings


def hash_password(password: str) -> str:
    """使用 bcrypt 对密码进行 hash"""
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def validate_password_strength(password: str) -> list[str]:
    """
    校验密码强度，返回错误列表（空列表表示通过）。
    规则：
    - 最少 8 位
    - 最多 128 位
    - 至少一个大写字母
    - 至少一个小写字母
    - 至少一个数字
    """
    errors = []
    if len(password) < 8:
        errors.append("密码长度至少为 8 位")
    if len(password) > 128:
        errors.append("密码长度不能超过 128 位")
    if not re.search(r'[A-Z]', password):
        errors.append("密码必须包含至少一个大写字母")
    if not re.search(r'[a-z]', password):
        errors.append("密码必须包含至少一个小写字母")
    if not re.search(r'[0-9]', password):
        errors.append("密码必须包含至少一个数字")
    return errors
```

### 6.2 JWT Token Payload 结构

```python
# access_token payload
{
    "sub": "uuid-string",           # 用户 ID（subject）
    "email": "user@example.com",    # 用户邮箱
    "account_type": "personal",     # 账号类型: "personal" | "team"
    "team_id": "uuid-string",       # 团队 ID（可为 null）
    "username": "testuser",         # 用户名
    "type": "access",              # token 类型标识
    "exp": 1720000000,             # 过期时间（Unix 时间戳）
    "iat": 1719999100,             # 签发时间
    "jti": "uuid-string"           # JWT ID，唯一标识，用于黑名单
}

# refresh_token payload
{
    "sub": "uuid-string",
    "email": "user@example.com",
    "account_type": "personal",
    "team_id": "uuid-string",
    "username": "testuser",
    "type": "refresh",
    "exp": 1722591100,             # 过期时间（30 天后）
    "iat": 1719999100,
    "jti": "uuid-string"
}
```

### 6.3 Token 生成函数

```python
# app/core/security.py — Phase 1 扩展

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt
from app.core.config import settings


def create_access_token(
    user_id: str,
    email: str,
    account_type: str,
    team_id: str | None,
    username: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """创建 access token"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "account_type": account_type,
        "team_id": team_id,
        "username": username,
        "type": "access",
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    expire = now + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
    payload["exp"] = expire
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: str,
    email: str,
    account_type: str,
    team_id: str | None,
    username: str,
) -> str:
    """创建 refresh token"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "account_type": account_type,
        "team_id": team_id,
        "username": username,
        "type": "refresh",
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload["exp"] = expire
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[dict]:
    """解码 JWT token，失败返回 None"""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except Exception:
        return None
```

### 6.4 邀请码生成

```python
# app/core/security.py — Phase 1 新增

import secrets
import string


def generate_invite_code(length: int = 6) -> str:
    """
    生成邀请码：大写字母 + 数字，排除易混淆字符。
    排除字符：0/O, 1/I/L
    """
    # 可用字符集：排除 0, O, 1, I, L 避免视觉混淆
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))
```

### 6.5 Redis Token 黑名单

```python
# app/core/security.py — Phase 1 新增

import hashlib
from app.core.redis import get_redis


async def blacklist_token(token: str, expires_at: datetime) -> None:
    """
    将 token 加入黑名单。
    TTL 为 token 剩余有效时间，过期后自动清理。
    """
    redis = get_redis()
    # 使用 token 的 SHA256 hash 作为 key，避免 key 过长
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    key = f"token_blacklist:{token_hash}"

    from datetime import timezone
    now = datetime.now(timezone.utc)
    ttl_seconds = int((expires_at - now).total_seconds())

    if ttl_seconds > 0:
        await redis.setex(key, ttl_seconds, "revoked")


async def is_token_blacklisted(token: str) -> bool:
    """检查 token 是否在黑名单中"""
    redis = get_redis()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    key = f"token_blacklist:{token_hash}"
    result = await redis.get(key)
    return result is not None
```

---

## 7. 权限中间件（依赖注入）

### 7.1 `get_current_user`（扩展 Phase 0）

```python
# app/api/deps.py — Phase 1 扩展

import uuid
from typing import Annotated
from datetime import datetime, timezone

from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import decode_token, is_token_blacklisted
from app.core.exceptions import UnauthorizedException
from app.models.user import User

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    从 JWT token 中解析用户信息并返回完整 User 对象。
    会检查 token 黑名单（Redis）。
    """
    token = credentials.credentials

    # 1. 解码 token
    payload = decode_token(token)
    if payload is None:
        raise UnauthorizedException("无效或过期的 Token")

    # 2. 检查 token 类型
    if payload.get("type") != "access":
        raise UnauthorizedException("Token 类型不正确")

    # 3. 检查 token 黑名单
    if await is_token_blacklisted(token):
        raise UnauthorizedException("Token 已被撤销")

    # 4. 获取用户 ID
    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise UnauthorizedException("无效 Token")

    # 5. 从数据库查询完整用户信息（保证数据是最新的）
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise UnauthorizedException("无效 Token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise UnauthorizedException("用户不存在")

    if not user.is_active:
        raise UnauthorizedException("账号已被禁用")

    return user


# 类型别名
CurrentUser = Annotated[User, Depends(get_current_user)]
DBSession = Annotated[AsyncSession, Depends(get_db)]
```

### 7.2 `require_owner` 依赖

```python
# app/api/deps.py — Phase 1 新增

from sqlalchemy import select
from app.models.team import Team
from app.core.exceptions import ForbiddenException


async def require_owner(
    current_user: CurrentUser,
    db: DBSession,
) -> Team:
    """
    检查当前用户是否为团队 owner。
    若是，返回关联的 Team 对象。
    若不是，抛出 403 ForbiddenException。
    """
    # 检查用户是否属于团队
    if current_user.team_id is None:
        raise ForbiddenException("您不属于任何团队")

    # 检查用户是否为团队 owner
    if current_user.account_type != "team":
        raise ForbiddenException("仅团队 Owner 可执行此操作")

    # 查询 Team 记录
    result = await db.execute(
        select(Team).where(Team.id == current_user.team_id)
    )
    team = result.scalar_one_or_none()

    if team is None:
        raise ForbiddenException("团队不存在")

    if team.owner_id != current_user.id:
        raise ForbiddenException("仅团队 Owner 可执行此操作")

    return team


# 类型别名
OwnerUser = Annotated[Team, Depends(require_owner)]
```

### 7.3 获取当前用户的 team（可选依赖）

```python
# app/api/deps.py — Phase 1 新增

from typing import Optional


async def get_current_team(
    current_user: CurrentUser,
    db: DBSession,
) -> Optional[Team]:
    """
    获取当前用户关联的团队信息（可选）。
    如果用户不属于任何团队，返回 None。
    """
    if current_user.team_id is None:
        return None

    result = await db.execute(
        select(Team).where(Team.id == current_user.team_id)
    )
    return result.scalar_one_or_none()
```

---

## 8. 服务层实现

### 8.1 `app/services/auth_service.py`

```python
"""认证服务：处理注册、登录、token 刷新、登出"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_invite_code,
    blacklist_token,
    is_token_blacklisted,
)
from app.core.exceptions import AppException, UnauthorizedException
from app.models.user import User
from app.models.team import Team


class AuthService:

    @staticmethod
    async def register(
        db: AsyncSession,
        email: str,
        username: str,
        password: str,
        account_type: str,
        team_name: str | None = None,
    ) -> dict:
        """
        用户注册。
        返回: {"user": User, "team": Team | None, "access_token": str, "refresh_token": str}
        """
        # 1. 检查邮箱是否已注册
        result = await db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none() is not None:
            raise AppException(
                code="EMAIL_ALREADY_REGISTERED",
                message="该邮箱已被注册",
                status_code=409,
            )

        # 2. 检查用户名是否已占用
        result = await db.execute(select(User).where(User.username == username))
        if result.scalar_one_or_none() is not None:
            raise AppException(
                code="USERNAME_ALREADY_TAKEN",
                message="该用户名已被占用",
                status_code=409,
            )

        # 3. 密码 hash
        password_hash = hash_password(password)

        # 4. 创建用户
        user = User(
            email=email,
            username=username,
            password_hash=password_hash,
            account_type=account_type,
            is_active=True,
        )
        db.add(user)
        await db.flush()  # flush 获取 user.id

        team = None

        # 5. 如果是团队注册，创建团队
        if account_type == "team" and team_name:
            invite_code = await AuthService._generate_unique_invite_code(db)
            team = Team(
                name=team_name,
                owner_id=user.id,
                invite_code=invite_code,
            )
            db.add(team)
            await db.flush()  # flush 获取 team.id

            # 更新用户的 team_id 和 account_type
            user.team_id = team.id
            user.account_type = "team"

        await db.commit()
        await db.refresh(user)
        if team:
            await db.refresh(team)

        # 6. 生成 tokens
        access_token = create_access_token(
            user_id=str(user.id),
            email=user.email,
            account_type=user.account_type,
            team_id=str(user.team_id) if user.team_id else None,
            username=user.username,
        )
        refresh_token = create_refresh_token(
            user_id=str(user.id),
            email=user.email,
            account_type=user.account_type,
            team_id=str(user.team_id) if user.team_id else None,
            username=user.username,
        )

        return {
            "user": user,
            "team": team,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    @staticmethod
    async def login(
        db: AsyncSession,
        email: str,
        password: str,
    ) -> dict:
        """
        用户登录。
        返回: {"user": User, "access_token": str, "refresh_token": str}
        """
        # 1. 查找用户
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None:
            raise AppException(
                code="INVALID_CREDENTIALS",
                message="邮箱或密码错误",
                status_code=401,
            )

        # 2. 检查账号状态
        if not user.is_active:
            raise AppException(
                code="ACCOUNT_DISABLED",
                message="账号已被禁用",
                status_code=403,
            )

        # 3. 验证密码
        if not verify_password(password, user.password_hash):
            raise AppException(
                code="INVALID_CREDENTIALS",
                message="邮箱或密码错误",
                status_code=401,
            )

        # 4. 生成 tokens
        access_token = create_access_token(
            user_id=str(user.id),
            email=user.email,
            account_type=user.account_type,
            team_id=str(user.team_id) if user.team_id else None,
            username=user.username,
        )
        refresh_token = create_refresh_token(
            user_id=str(user.id),
            email=user.email,
            account_type=user.account_type,
            team_id=str(user.team_id) if user.team_id else None,
            username=user.username,
        )

        return {
            "user": user,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    @staticmethod
    async def refresh_token(
        db: AsyncSession,
        token: str,
    ) -> dict:
        """
        刷新 access token。
        返回: {"access_token": str, "expires_in": int}
        """
        from app.core.config import settings

        # 1. 解码 token
        payload = decode_token(token)
        if payload is None:
            raise AppException(
                code="INVALID_TOKEN",
                message="Token 无效或已过期",
                status_code=401,
            )

        # 2. 检查 token 类型
        if payload.get("type") != "refresh":
            raise AppException(
                code="INVALID_TOKEN_TYPE",
                message="需要 refresh_token",
                status_code=401,
            )

        # 3. 检查黑名单
        if await is_token_blacklisted(token):
            raise AppException(
                code="TOKEN_REVOKED",
                message="Token 已被撤销",
                status_code=401,
            )

        # 4. 查询用户
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise AppException(code="INVALID_TOKEN", message="无效 Token", status_code=401)

        result = await db.execute(
            select(User).where(User.id == uuid.UUID(user_id_str))
        )
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            raise AppException(
                code="USER_INACTIVE",
                message="用户不存在或已被禁用",
                status_code=401,
            )

        # 5. 生成新的 access_token
        access_token = create_access_token(
            user_id=str(user.id),
            email=user.email,
            account_type=user.account_type,
            team_id=str(user.team_id) if user.team_id else None,
            username=user.username,
        )

        return {
            "access_token": access_token,
            "expires_in": settings.jwt_access_token_expire_minutes * 60,
        }

    @staticmethod
    async def logout(token: str, payload: dict) -> None:
        """将 access_token 加入黑名单"""
        exp_timestamp = payload.get("exp")
        if exp_timestamp:
            expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
            await blacklist_token(token, expires_at)

    @staticmethod
    async def _generate_unique_invite_code(db: AsyncSession) -> str:
        """生成唯一的邀请码（最多重试 3 次）"""
        for _ in range(3):
            code = generate_invite_code()
            result = await db.execute(
                select(Team).where(Team.invite_code == code)
            )
            if result.scalar_one_or_none() is None:
                return code
        raise AppException(
            code="INVITE_CODE_GENERATION_FAILED",
            message="邀请码生成失败，请重试",
            status_code=500,
        )
```

### 8.2 `app/services/user_service.py`

```python
"""用户服务：处理个人资料查看/更新、密码修改"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.core.exceptions import AppException
from app.models.user import User
from app.models.team import Team


class UserService:

    @staticmethod
    async def get_profile(db: AsyncSession, user: User) -> dict:
        """
        获取用户完整资料（含团队信息）。
        返回: {"user": User, "team": Team | None}
        """
        team = None
        if user.team_id:
            result = await db.execute(
                select(Team).where(Team.id == user.team_id)
            )
            team = result.scalar_one_or_none()

        return {"user": user, "team": team}

    @staticmethod
    async def update_user(
        db: AsyncSession,
        user: User,
        username: str | None = None,
    ) -> User:
        """更新用户信息"""
        if username is None:
            raise AppException(
                code="NO_FIELDS_TO_UPDATE",
                message="未提供任何需要更新的字段",
                status_code=400,
            )

        # 检查用户名唯一性
        if username is not None:
            result = await db.execute(
                select(User).where(User.username == username, User.id != user.id)
            )
            if result.scalar_one_or_none() is not None:
                raise AppException(
                    code="USERNAME_ALREADY_TAKEN",
                    message="该用户名已被占用",
                    status_code=409,
                )
            user.username = username

        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def change_password(
        db: AsyncSession,
        user: User,
        old_password: str,
        new_password: str,
    ) -> None:
        """修改密码"""
        # 1. 验证旧密码
        if not verify_password(old_password, user.password_hash):
            raise AppException(
                code="INVALID_OLD_PASSWORD",
                message="旧密码不正确",
                status_code=400,
            )

        # 2. 检查新旧密码是否相同
        if old_password == new_password:
            raise AppException(
                code="SAME_PASSWORD",
                message="新密码不能与旧密码相同",
                status_code=400,
            )

        # 3. 更新密码
        user.password_hash = hash_password(new_password)
        await db.commit()
```

### 8.3 `app/services/team_service.py`

```python
"""团队服务：处理团队创建、加入、成员管理、删除"""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_invite_code
from app.core.exceptions import AppException
from app.core.config import settings
from app.models.user import User
from app.models.team import Team


class TeamService:

    @staticmethod
    async def create_team(
        db: AsyncSession,
        user: User,
        name: str,
    ) -> dict:
        """
        个人用户创建团队。
        返回: {"team": Team, "user": User}
        """
        # 1. 检查用户是否已有团队
        if user.account_type == "team":
            raise AppException(
                code="ALREADY_HAS_TEAM",
                message="您已拥有一个团队",
                status_code=409,
            )

        # 2. 检查用户是否已加入其他团队
        if user.team_id is not None:
            raise AppException(
                code="ALREADY_IN_TEAM",
                message="您已加入其他团队，请先退出后再创建",
                status_code=409,
            )

        # 3. 生成邀请码
        invite_code = await TeamService._generate_unique_invite_code(db)

        # 4. 创建团队
        team = Team(
            name=name,
            owner_id=user.id,
            invite_code=invite_code,
        )
        db.add(team)
        await db.flush()

        # 5. 更新用户
        user.team_id = team.id
        user.account_type = "team"

        await db.commit()
        await db.refresh(team)
        await db.refresh(user)

        return {"team": team, "user": user}

    @staticmethod
    async def join_team(
        db: AsyncSession,
        user: User,
        invite_code: str,
    ) -> dict:
        """
        通过邀请码加入团队。
        返回: {"team": Team, "user": User}
        """
        # 1. 检查用户状态
        if user.account_type == "team":
            raise AppException(
                code="ALREADY_HAS_TEAM",
                message="您已拥有一个团队，无法加入其他团队",
                status_code=409,
            )
        if user.team_id is not None:
            raise AppException(
                code="ALREADY_IN_TEAM",
                message="您已在一个团队中，请先退出当前团队",
                status_code=409,
            )

        # 2. 查找团队
        invite_code_upper = invite_code.upper()
        result = await db.execute(
            select(Team).where(Team.invite_code == invite_code_upper)
        )
        team = result.scalar_one_or_none()
        if team is None:
            raise AppException(
                code="INVALID_INVITE_CODE",
                message="邀请码无效",
                status_code=404,
            )

        # 3. 检查团队人数
        member_count_result = await db.execute(
            select(func.count()).select_from(User).where(User.team_id == team.id)
        )
        member_count = member_count_result.scalar()
        if member_count >= settings.team_max_members:
            raise AppException(
                code="TEAM_FULL",
                message=f"团队人数已达上限（{settings.team_max_members}人）",
                status_code=400,
            )

        # 4. 加入团队
        user.team_id = team.id
        # account_type 保持 "personal"

        await db.commit()
        await db.refresh(user)

        return {"team": team, "user": user}

    @staticmethod
    async def get_members(
        db: AsyncSession,
        team: Team,
    ) -> list[dict]:
        """获取团队所有成员"""
        result = await db.execute(
            select(User).where(User.team_id == team.id)
        )
        members = result.scalars().all()

        member_list = []
        for member in members:
            role = "owner" if member.id == team.owner_id else "member"
            member_list.append({
                "id": member.id,
                "email": member.email,
                "username": member.username,
                "avatar_url": member.avatar_url,
                "account_type": member.account_type,
                "role": role,
                "joined_at": member.updated_at,
            })

        return member_list

    @staticmethod
    async def remove_member(
        db: AsyncSession,
        team: Team,
        owner_user: User,
        target_user_id: str,
    ) -> None:
        """移除团队成员"""
        import uuid

        # 1. 不能移除自己
        if str(owner_user.id) == target_user_id:
            raise AppException(
                code="CANNOT_REMOVE_SELF",
                message="不能移除自己，如需离开请使用删除团队功能",
                status_code=400,
            )

        # 2. 查找目标用户
        result = await db.execute(
            select(User).where(User.id == uuid.UUID(target_user_id))
        )
        target_user = result.scalar_one_or_none()
        if target_user is None:
            raise AppException(
                code="USER_NOT_FOUND",
                message="用户不存在",
                status_code=404,
            )

        # 3. 检查目标用户是否在团队中
        if target_user.team_id != team.id:
            raise AppException(
                code="USER_NOT_IN_TEAM",
                message="该用户不属于当前团队",
                status_code=400,
            )

        # 4. 移除：清除 team_id
        target_user.team_id = None
        # account_type 保持 personal

        await db.commit()

    @staticmethod
    async def reset_invite_code(
        db: AsyncSession,
        team: Team,
    ) -> str:
        """重置团队邀请码，返回新邀请码"""
        new_code = await TeamService._generate_unique_invite_code(db)
        team.invite_code = new_code
        await db.commit()
        return new_code

    @staticmethod
    async def delete_team(
        db: AsyncSession,
        team: Team,
        owner_user: User,
    ) -> int:
        """
        删除团队。所有成员回退为个人用户。
        返回受影响的成员数。
        """
        # 1. 查询所有成员（不含 owner）
        result = await db.execute(
            select(User).where(User.team_id == team.id, User.id != owner_user.id)
        )
        members = result.scalars().all()
        affected_count = len(members)

        # 2. 批量更新成员：清除 team_id
        for member in members:
            member.team_id = None
            # account_type 保持 personal

        # 3. 更新 owner：清除 team_id，恢复 personal
        owner_user.team_id = None
        owner_user.account_type = "personal"

        # 4. 删除团队
        await db.delete(team)

        await db.commit()
        return affected_count

    @staticmethod
    async def _generate_unique_invite_code(db: AsyncSession) -> str:
        """生成唯一的邀请码"""
        for _ in range(3):
            code = generate_invite_code()
            result = await db.execute(
                select(Team).where(Team.invite_code == code)
            )
            if result.scalar_one_or_none() is None:
                return code
        raise AppException(
            code="INVITE_CODE_GENERATION_FAILED",
            message="邀请码生成失败，请重试",
            status_code=500,
        )
```

---

## 9. 路由层实现

### 9.1 路由注册变更

修改 `app/api/router.py`，注册 Phase 1 新路由：

```python
# app/api/router.py — Phase 1 修改

from fastapi import APIRouter
from app.api.v1 import health, auth, users, teams

api_router = APIRouter(prefix="/api")

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])        # Phase 1 新增
api_router.include_router(users.router, prefix="/users", tags=["Users"])     # Phase 1 实现
api_router.include_router(teams.router, prefix="/teams", tags=["Teams"])     # Phase 1 新增

# ... 其他 Phase 0 骨架路由保持不变 ...
```

### 9.2 认证路由 `app/api/v1/auth.py`

```python
# app/api/v1/auth.py

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.auth import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    LogoutResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
)
from app.schemas.user import UserResponse
from app.schemas.team import TeamResponse
from app.services.auth_service import AuthService
from app.services.user_service import UserService

router = APIRouter()


@router.post("/register", response_model=dict)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """用户注册"""
    result = await AuthService.register(
        db=db,
        email=body.email,
        username=body.username,
        password=body.password,
        account_type=body.account_type,
        team_name=body.team_name,
    )

    response_data = {
        "code": 0,
        "message": "success",
        "data": {
            "user": UserResponse.model_validate(result["user"]).model_dump(),
            "team": TeamResponse.model_validate(result["team"]).model_dump() if result["team"] else None,
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"],
            "token_type": "bearer",
        }
    }
    return response_data


@router.post("/login", response_model=dict)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """用户登录"""
    result = await AuthService.login(
        db=db,
        email=body.email,
        password=body.password,
    )

    return {
        "code": 0,
        "message": "success",
        "data": {
            "user": UserResponse.model_validate(result["user"]).model_dump(),
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"],
            "token_type": "bearer",
        }
    }


@router.post("/refresh", response_model=dict)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """刷新 access token"""
    result = await AuthService.refresh_token(
        db=db,
        token=body.refresh_token,
    )

    return {
        "code": 0,
        "message": "success",
        "data": result,
    }


@router.post("/logout", response_model=dict)
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """用户登出"""
    # 从 header 中提取 token
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""

    # 解码获取 exp
    from app.core.security import decode_token
    payload = decode_token(token)

    if payload:
        await AuthService.logout(token=token, payload=payload)

    return {
        "code": 0,
        "message": "success",
        "data": {"message": "登出成功"},
    }
```

### 9.3 用户路由 `app/api/v1/users.py`

```python
# app/api/v1/users.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest
from app.schemas.user import UserUpdateRequest, UserProfileResponse
from app.schemas.team import TeamResponse
from app.services.user_service import UserService

router = APIRouter()


@router.get("/me", response_model=dict)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户信息"""
    result = await UserService.get_profile(db=db, user=current_user)

    user_data = UserProfileResponse(
        id=result["user"].id,
        email=result["user"].email,
        username=result["user"].username,
        avatar_url=result["user"].avatar_url,
        account_type=result["user"].account_type,
        team_id=result["user"].team_id,
        team=TeamResponse.model_validate(result["team"]) if result["team"] else None,
        is_active=result["user"].is_active,
        created_at=result["user"].created_at,
        updated_at=result["user"].updated_at,
    )

    return {
        "code": 0,
        "message": "success",
        "data": user_data.model_dump(),
    }


@router.patch("/me", response_model=dict)
async def update_me(
    body: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新用户信息"""
    updated_user = await UserService.update_user(
        db=db,
        user=current_user,
        username=body.username,
    )

    result = await UserService.get_profile(db=db, user=updated_user)

    user_data = UserProfileResponse(
        id=result["user"].id,
        email=result["user"].email,
        username=result["user"].username,
        avatar_url=result["user"].avatar_url,
        account_type=result["user"].account_type,
        team_id=result["user"].team_id,
        team=TeamResponse.model_validate(result["team"]) if result["team"] else None,
        is_active=result["user"].is_active,
        created_at=result["user"].created_at,
        updated_at=result["user"].updated_at,
    )

    return {
        "code": 0,
        "message": "success",
        "data": user_data.model_dump(),
    }


@router.post("/me/change-password", response_model=dict)
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改密码"""
    await UserService.change_password(
        db=db,
        user=current_user,
        old_password=body.old_password,
        new_password=body.new_password,
    )

    return {
        "code": 0,
        "message": "success",
        "data": {"message": "密码修改成功"},
    }
```

### 9.4 团队路由 `app/api/v1/teams.py`

```python
# app/api/v1/teams.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user, require_owner
from app.models.user import User
from app.models.team import Team
from app.schemas.team import (
    TeamCreateRequest,
    JoinTeamRequest,
    TeamResponse,
    TeamMemberResponse,
    TeamMembersResponse,
)
from app.schemas.user import UserResponse
from app.services.team_service import TeamService

router = APIRouter()


@router.post("", response_model=dict)
async def create_team(
    body: TeamCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建团队"""
    result = await TeamService.create_team(
        db=db,
        user=current_user,
        name=body.name,
    )

    return {
        "code": 0,
        "message": "success",
        "data": {
            "team": TeamResponse.model_validate(result["team"]).model_dump(),
            "user": UserResponse.model_validate(result["user"]).model_dump(),
        },
    }


@router.post("/join", response_model=dict)
async def join_team(
    body: JoinTeamRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """加入团队"""
    result = await TeamService.join_team(
        db=db,
        user=current_user,
        invite_code=body.invite_code,
    )

    # 计算成员数
    from sqlalchemy import select, func
    member_count_result = await db.execute(
        select(func.count()).select_from(User).where(User.team_id == result["team"].id)
    )
    member_count = member_count_result.scalar()

    team_data = TeamResponse.model_validate(result["team"]).model_dump()
    team_data["member_count"] = member_count

    return {
        "code": 0,
        "message": "success",
        "data": {
            "team": team_data,
            "user": UserResponse.model_validate(result["user"]).model_dump(),
        },
    }


@router.get("/members", response_model=dict)
async def get_members(
    current_user: User = Depends(get_current_user),
    team: Team = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """获取团队成员列表（仅 owner）"""
    members = await TeamService.get_members(db=db, team=team)

    return {
        "code": 0,
        "message": "success",
        "data": {
            "team_id": str(team.id),
            "team_name": team.name,
            "members": members,
            "total": len(members),
        },
    }


@router.delete("/members/{user_id}", response_model=dict)
async def remove_member(
    user_id: str,
    current_user: User = Depends(get_current_user),
    team: Team = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """移除团队成员（仅 owner）"""
    await TeamService.remove_member(
        db=db,
        team=team,
        owner_user=current_user,
        target_user_id=user_id,
    )

    return {
        "code": 0,
        "message": "success",
        "data": {"message": "成员已移除"},
    }


@router.post("/invite-code/reset", response_model=dict)
async def reset_invite_code(
    current_user: User = Depends(get_current_user),
    team: Team = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """重置邀请码（仅 owner）"""
    new_code = await TeamService.reset_invite_code(db=db, team=team)

    return {
        "code": 0,
        "message": "success",
        "data": {
            "invite_code": new_code,
            "message": "邀请码已重置",
        },
    }


@router.delete("", response_model=dict)
async def delete_team(
    current_user: User = Depends(get_current_user),
    team: Team = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """删除团队（仅 owner）"""
    affected = await TeamService.delete_team(
        db=db,
        team=team,
        owner_user=current_user,
    )

    return {
        "code": 0,
        "message": "success",
        "data": {
            "message": "团队已删除",
            "affected_members": affected,
        },
    }
```

---

## 10. Pydantic Schemas 完整定义

### 10.1 `app/schemas/auth.py`

```python
"""认证相关 Schema"""

import re
import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    """注册请求"""
    email: EmailStr
    username: str = Field(..., min_length=2, max_length=100, description="用户名")
    password: str = Field(..., min_length=8, max_length=128, description="密码")
    account_type: str = Field(
        default="personal",
        pattern="^(personal|team)$",
        description="账号类型: personal(个人) 或 team(团队)",
    )
    team_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="团队名称（仅团队注册时必填）",
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r'^[\w\u4e00-\u9fff\-]+$', v):
            raise ValueError("用户名仅支持中英文、数字、下划线和短横线")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("用户名不能以短横线开头或结尾")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r'[A-Z]', v):
            raise ValueError("密码必须包含至少一个大写字母")
        if not re.search(r'[a-z]', v):
            raise ValueError("密码必须包含至少一个小写字母")
        if not re.search(r'[0-9]', v):
            raise ValueError("密码必须包含至少一个数字")
        return v

    @field_validator("team_name")
    @classmethod
    def validate_team_name(cls, v, info):
        account_type = info.data.get("account_type")
        if account_type == "team" and not v:
            raise ValueError("团队注册时必须提供 team_name")
        return v


class LoginRequest(BaseModel):
    """登录请求"""
    email: EmailStr
    password: str = Field(..., min_length=1)


class RefreshRequest(BaseModel):
    """刷新 Token 请求"""
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if not re.search(r'[A-Z]', v):
            raise ValueError("密码必须包含至少一个大写字母")
        if not re.search(r'[a-z]', v):
            raise ValueError("密码必须包含至少一个小写字母")
        if not re.search(r'[0-9]', v):
            raise ValueError("密码必须包含至少一个数字")
        return v


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
```

### 10.2 `app/schemas/user.py`（Phase 1 修改后）

```python
"""用户相关 Schema"""

import re
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


class UserResponse(BaseModel):
    """用户基本信息响应"""
    id: uuid.UUID
    email: str
    username: str
    avatar_url: Optional[str] = None
    account_type: str
    team_id: Optional[uuid.UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserProfileResponse(BaseModel):
    """用户完整资料响应（含团队信息）"""
    id: uuid.UUID
    email: str
    username: str
    avatar_url: Optional[str] = None
    account_type: str
    team_id: Optional[uuid.UUID] = None
    team: Optional[dict] = None  # TeamResponse 的 dict 形式，避免循环引用
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    """更新用户信息请求"""
    username: Optional[str] = Field(default=None, min_length=2, max_length=100)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r'^[\w\u4e00-\u9fff\-]+$', v):
            raise ValueError("用户名仅支持中英文、数字、下划线和短横线")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("用户名不能以短横线开头或结尾")
        return v
```

### 10.3 `app/schemas/team.py`

```python
"""团队相关 Schema"""

import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class TeamCreateRequest(BaseModel):
    """创建团队请求"""
    name: str = Field(..., min_length=1, max_length=200, description="团队名称")


class JoinTeamRequest(BaseModel):
    """加入团队请求"""
    invite_code: str = Field(..., min_length=6, max_length=6, description="6位邀请码")


class TeamResponse(BaseModel):
    """团队信息响应"""
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    invite_code: str
    member_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TeamMemberResponse(BaseModel):
    """团队成员信息"""
    id: uuid.UUID
    email: str
    username: str
    avatar_url: Optional[str] = None
    account_type: str
    role: str  # "owner" 或 "member"
    joined_at: datetime

    model_config = {"from_attributes": True}


class TeamMembersResponse(BaseModel):
    """团队成员列表响应"""
    team_id: uuid.UUID
    team_name: str
    members: List[TeamMemberResponse]
    total: int
```

---

## 11. 错误码完整定义

### 11.1 认证相关

| HTTP 状态码 | 业务错误码 | 触发场景 | 说明 |
|------------|-----------|---------|------|
| 401 | `INVALID_CREDENTIALS` | 登录时邮箱或密码错误 | 不区分用户不存在和密码错误 |
| 401 | `INVALID_TOKEN` | Token 解码失败或已过期 | access/refresh token 均适用 |
| 401 | `INVALID_TOKEN_TYPE` | refresh 接口收到 access_token | token type 不匹配 |
| 401 | `TOKEN_REVOKED` | 使用已登出的 token | token 在黑名单中 |
| 401 | `USER_INACTIVE` | 用户不存在或已禁用 | refresh 时检查用户状态 |
| 401 | `UNAUTHORIZED` | 未携带 token 或 token 格式错误 | 通用认证失败 |
| 403 | `ACCOUNT_DISABLED` | 已登录但账号被禁用 | is_active=false |
| 409 | `EMAIL_ALREADY_REGISTERED` | 注册时邮箱重复 | 唯一约束冲突 |
| 409 | `USERNAME_ALREADY_TAKEN` | 注册/修改时用户名重复 | 唯一约束冲突 |
| 400 | `INVALID_OLD_PASSWORD` | 修改密码时旧密码错误 | - |
| 400 | `SAME_PASSWORD` | 新密码与旧密码相同 | - |

### 11.2 用户相关

| HTTP 状态码 | 业务错误码 | 触发场景 | 说明 |
|------------|-----------|---------|------|
| 400 | `NO_FIELDS_TO_UPDATE` | PATCH /me 未提供任何字段 | - |
| 422 | `VALIDATION_ERROR` | 请求体字段校验失败 | Pydantic 校验自动触发 |

### 11.3 团队相关

| HTTP 状态码 | 业务错误码 | 触发场景 | 说明 |
|------------|-----------|---------|------|
| 409 | `ALREADY_HAS_TEAM` | 创建团队时用户已有团队 | - |
| 409 | `ALREADY_IN_TEAM` | 创建/加入团队时已在其他团队 | - |
| 404 | `INVALID_INVITE_CODE` | 加入团队时邀请码无效 | - |
| 400 | `TEAM_FULL` | 加入团队时人数已满 | 超过 team_max_members |
| 403 | `OWNER_ONLY` | 非 owner 执行 owner 操作 | - |
| 403 | `NOT_IN_TEAM` | 用户不属于任何团队 | - |
| 400 | `CANNOT_REMOVE_SELF` | owner 尝试移除自己 | - |
| 404 | `USER_NOT_FOUND` | 移除成员时目标用户不存在 | - |
| 400 | `USER_NOT_IN_TEAM` | 移除成员时目标不在团队中 | - |
| 500 | `INVITE_CODE_GENERATION_FAILED` | 邀请码生成重试 3 次仍重复 | 极端情况 |

### 11.4 通用错误

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 422 | `VALIDATION_ERROR` | FastAPI 参数校验失败 |
| 404 | `NOT_FOUND` | 路由不存在 |
| 405 | `METHOD_NOT_ALLOWED` | HTTP 方法不允许 |
| 500 | `INTERNAL_ERROR` | 服务器内部错误 |

---

## 12. 与 Phase 0 的衔接说明

### 12.1 复用的模块

| Phase 0 模块 | Phase 1 如何使用 |
|-------------|----------------|
| `app/core/config.py` | 扩展新增 `bcrypt_rounds`、`team_max_members` 等配置字段 |
| `app/core/database.py` | 直接复用 `get_db` 依赖 |
| `app/core/redis.py` | 直接复用 `get_redis()`，用于 token 黑名单 |
| `app/core/security.py` | 扩展 `hash_password`、`verify_password`、`decode_token`，新增 `create_access_token`、`create_refresh_token`、`generate_invite_code`、`blacklist_token`、`is_token_blacklisted` |
| `app/core/exceptions.py` | 直接复用 `AppException`、`UnauthorizedException`、`ForbiddenException`、`NotFoundException` |
| `app/core/logging.py` | 不修改 |
| `app/models/base.py` | 不修改，复用 `Base`、`UUIDPrimaryKeyMixin`、`TimestampMixin` |
| `app/models/user.py` | **扩展**：新增 `username`、`account_type`、`team_id`、`is_active` 字段 |
| `app/middleware/request_log.py` | 不修改 |
| `app/middleware/error_handler.py` | 不修改 |
| `app/api/deps.py` | 扩展 `get_current_user`（加入黑名单检查），新增 `require_owner`、`get_current_team` |
| `app/api/router.py` | 修改：注册 auth、users、teams 路由 |

### 12.2 新增的文件

| 文件路径 | 说明 |
|---------|------|
| `app/models/team.py` | Team 模型 |
| `app/schemas/auth.py` | 认证请求/响应 Schema |
| `app/schemas/team.py` | 团队请求/响应 Schema |
| `app/services/__init__.py` | 服务层包 |
| `app/services/auth_service.py` | 认证业务逻辑 |
| `app/services/user_service.py` | 用户业务逻辑 |
| `app/services/team_service.py` | 团队业务逻辑 |
| `app/api/v1/auth.py` | 认证路由 |
| `app/api/v1/teams.py` | 团队路由 |

### 12.3 修改的文件

| 文件路径 | 修改内容 |
|---------|---------|
| `app/core/config.py` | 新增 Phase 1 配置字段 |
| `app/core/security.py` | 扩展密码处理、JWT 生成、邀请码生成、token 黑名单 |
| `app/models/user.py` | 扩展 User 模型字段和关系 |
| `app/models/__init__.py` | 导出 Team 模型 |
| `app/models/enums.py` | 新增 AccountType 枚举 |
| `app/schemas/user.py` | 扩展 UserResponse、新增 UserProfileResponse、UserUpdateRequest |
| `app/api/deps.py` | 扩展 get_current_user、新增 require_owner |
| `app/api/router.py` | 注册 auth/teams 路由 |
| `app/api/v1/users.py` | 从空骨架实现完整用户路由 |
| `.env.example` | 新增 Phase 1 配置项 |

### 12.4 需要执行的命令

```bash
# 1. 更新依赖（如果需要）
pip install python-jose[cryptography] bcrypt redis

# 2. 生成数据库迁移
alembic revision --autogenerate -m "phase1_user_system"

# 3. 执行迁移
alembic upgrade head

# 4. 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 13. 业务逻辑详细说明

### 13.1 注册流程详解

```
客户端请求 POST /api/auth/register
    │
    ├─ Pydantic 校验请求体
    │   ├─ email 格式校验
    │   ├─ username 格式校验（中英文/数字/下划线/短横线，2-100字符）
    │   ├─ password 强度校验（≥8位，含大小写+数字）
    │   ├─ account_type 枚举校验（personal/team）
    │   └─ 如果 account_type=team，team_name 必填
    │
    ├─ 业务校验
    │   ├─ 查询 email 是否已存在 → 409 EMAIL_ALREADY_REGISTERED
    │   └─ 查询 username 是否已存在 → 409 USERNAME_ALREADY_TAKEN
    │
    ├─ 密码处理
    │   └─ bcrypt.hashpw(password, bcrypt.gensalt(rounds=12))
    │
    ├─ 创建 User 记录
    │   └─ INSERT INTO users (email, username, password_hash, account_type, is_active)
    │
    ├─ 如果是团队注册
    │   ├─ 生成 6 位邀请码（排除 0/O/1/I/L）
    │   ├─ 检查邀请码唯一性（最多重试 3 次）
    │   ├─ INSERT INTO teams (name, owner_id, invite_code)
    │   └─ UPDATE users SET team_id=team.id, account_type='team' WHERE id=user.id
    │
    ├─ 生成 JWT tokens
    │   ├─ access_token: sub=user.id, type=access, exp=now+15min
    │   └─ refresh_token: sub=user.id, type=refresh, exp=now+30days
    │
    └─ 返回响应
        ├─ user: UserResponse
        ├─ team: TeamResponse | null
        ├─ access_token
        └─ refresh_token
```

### 13.2 登录流程详解

```
客户端请求 POST /api/auth/login
    │
    ├─ Pydantic 校验：email 格式 + password 非空
    │
    ├─ 查询用户：SELECT * FROM users WHERE email = ?
    │   └─ 不存在 → 401 INVALID_CREDENTIALS
    │
    ├─ 检查 is_active
    │   └─ false → 403 ACCOUNT_DISABLED
    │
    ├─ 验证密码：bcrypt.checkpw(plain, hash)
    │   └─ 不匹配 → 401 INVALID_CREDENTIALS
    │
    ├─ 生成 tokens（同注册流程）
    │
    └─ 返回响应
```

### 13.3 Token 刷新流程详解

```
客户端请求 POST /api/auth/refresh
    Body: { "refresh_token": "..." }
    │
    ├─ 解码 refresh_token
    │   └─ 失败 → 401 INVALID_TOKEN
    │
    ├─ 检查 type == "refresh"
    │   └─ 不是 → 401 INVALID_TOKEN_TYPE
    │
    ├─ 检查 Redis 黑名单
    │   └─ 在黑名单中 → 401 TOKEN_REVOKED
    │
    ├─ 查询用户（根据 sub）
    │   └─ 不存在或 is_active=false → 401 USER_INACTIVE
    │
    ├─ 生成新的 access_token（使用最新用户数据）
    │
    └─ 返回 { access_token, expires_in }
```

### 13.4 登出流程详解

```
客户端请求 POST /api/auth/logout
    Header: Authorization: Bearer <access_token>
    │
    ├─ 验证 access_token（get_current_user 依赖）
    │
    ├─ 从 token 中提取 exp（过期时间）
    │
    ├─ 计算 TTL = exp - now
    │
    ├─ 写入 Redis
    │   └─ SET token_blacklist:{sha256(token)} "revoked" EX {ttl}
    │
    └─ 返回成功
```

### 13.5 加入团队流程详解

```
客户端请求 POST /api/teams/join
    Body: { "invite_code": "ABC123" }
    │
    ├─ 检查用户状态
    │   ├─ account_type == "team" → 409 ALREADY_HAS_TEAM
    │   └─ team_id != None → 409 ALREADY_IN_TEAM
    │
    ├─ 邀请码转大写
    │
    ├─ 查询团队：SELECT * FROM teams WHERE invite_code = ?
    │   └─ 不存在 → 404 INVALID_INVITE_CODE
    │
    ├─ 统计成员数：SELECT COUNT(*) FROM users WHERE team_id = team.id
    │   └─ >= team_max_members → 400 TEAM_FULL
    │
    ├─ 更新用户：UPDATE users SET team_id = team.id WHERE id = user.id
    │   └─ account_type 保持 "personal"
    │
    └─ 返回团队信息和更新后的用户信息
```

### 13.6 删除 Owner 的级联逻辑

```
当 owner 用户被删除时（假设未来有 DELETE /api/users/me 接口）：
    │
    ├─ 查询 owner 关联的 team
    │
    ├─ 如果存在关联团队
    │   ├─ 查询团队所有成员（team_id = team.id）
    │   ├─ 批量更新所有成员：
    │   │   UPDATE users SET team_id = NULL WHERE team_id = team.id
    │   │   └─ account_type 保持 personal（成员本来就是 personal）
    │   ├─ 删除 team 记录
    │   └─ 删除 user 记录（CASCADE 自动处理）
    │
    └─ 注意：Phase 1 不实现 DELETE /api/users/me，此逻辑为未来预留
```

### 13.7 删除团队流程详解

```
团队 owner 请求 DELETE /api/teams
    │
    ├─ 权限校验：require_owner
    │
    ├─ 查询团队所有成员
    │
    ├─ 批量更新非 owner 成员：
    │   UPDATE users SET team_id = NULL WHERE team_id = team.id AND id != owner.id
    │   └─ account_type 保持 personal
    │
    ├─ 更新 owner：
    │   UPDATE users SET team_id = NULL, account_type = 'personal' WHERE id = owner.id
    │
    ├─ 删除 team 记录
    │
    └─ 返回受影响成员数
```

### 13.8 重置邀请码流程详解

```
团队 owner 请求 POST /api/teams/invite-code/reset
    │
    ├─ 权限校验：require_owner
    │
    ├─ 生成新邀请码（6位，大写字母+数字，排除易混淆字符）
    │
    ├─ 检查唯一性（最多重试 3 次）
    │
    ├─ 更新团队：UPDATE teams SET invite_code = ? WHERE id = team.id
    │
    └─ 返回新邀请码
```

---

## 14. 级联规则总结

| 操作 | 影响范围 |
|------|---------|
| 删除 team owner 用户 | 删除关联团队 → 团队所有成员 `team_id=NULL`, `account_type=personal`（Phase 1 不实现此接口，预留规则） |
| 删除团队（`DELETE /api/teams`） | 所有成员 `team_id=NULL`，owner `account_type` 回退为 `personal` |
| 移除成员（`DELETE /api/teams/members/{id}`） | 被移除成员 `team_id=NULL`，`account_type` 保持 `personal` |
| 创建团队 | 创建者 `account_type` 变为 `team`，`team_id` 指向新团队 |
| 加入团队 | 加入者 `team_id` 指向团队，`account_type` 保持 `personal` |

---

## 15. 测试用例

### 15.1 测试配置 `tests/conftest.py`（Phase 1 扩展）

```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.core.database import get_db
from app.core.config import settings
from app.core.security import hash_password, create_access_token
from app.models.base import Base
from app.models.user import User
from app.models.team import Team


# 测试数据库 URL（使用不同的数据库避免污染开发数据）
TEST_DATABASE_URL = settings.database_url.replace("tangyuan_db", "tangyuan_test")


@pytest_asyncio.fixture
async def db_session():
    """创建测试数据库 session"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    """创建测试 HTTP 客户端"""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """创建一个测试个人用户"""
    user = User(
        email="test@example.com",
        username="testuser",
        password_hash=hash_password("TestPass123"),
        account_type="personal",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def team_owner(db_session: AsyncSession) -> User:
    """创建一个测试团队 owner"""
    user = User(
        email="owner@example.com",
        username="teamowner",
        password_hash=hash_password("TestPass123"),
        account_type="team",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    team = Team(
        name="Test Team",
        owner_id=user.id,
        invite_code="ABC123",
    )
    db_session.add(team)
    await db_session.commit()
    await db_session.refresh(team)

    user.team_id = team.id
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user: User) -> dict:
    """生成测试用户的认证头"""
    token = create_access_token(
        user_id=str(test_user.id),
        email=test_user.email,
        account_type=test_user.account_type,
        team_id=None,
        username=test_user.username,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def owner_headers(team_owner: User) -> dict:
    """生成团队 owner 的认证头"""
    token = create_access_token(
        user_id=str(team_owner.id),
        email=team_owner.email,
        account_type=team_owner.account_type,
        team_id=str(team_owner.team_id),
        username=team_owner.username,
    )
    return {"Authorization": f"Bearer {token}"}
```

### 15.2 注册接口测试 `tests/test_auth_register.py`

```python
import pytest


@pytest.mark.asyncio
class TestRegister:
    """注册接口测试"""

    async def test_personal_register_success(self, client):
        """个人注册 - 正常流程"""
        response = await client.post("/api/auth/register", json={
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "MyPass123",
            "account_type": "personal",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        assert data["data"]["user"]["email"] == "newuser@example.com"
        assert data["data"]["user"]["account_type"] == "personal"
        assert data["data"]["team"] is None

    async def test_team_register_success(self, client):
        """团队注册 - 正常流程"""
        response = await client.post("/api/auth/register", json={
            "email": "team@example.com",
            "username": "teamowner",
            "password": "MyPass123",
            "account_type": "team",
            "team_name": "My Team",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["user"]["account_type"] == "team"
        assert data["data"]["team"] is not None
        assert data["data"]["team"]["name"] == "My Team"
        assert len(data["data"]["team"]["invite_code"]) == 6

    async def test_register_duplicate_email(self, client, test_user):
        """注册 - 邮箱重复"""
        response = await client.post("/api/auth/register", json={
            "email": "test@example.com",  # 已存在
            "username": "anotheruser",
            "password": "MyPass123",
        })
        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "EMAIL_ALREADY_REGISTERED"

    async def test_register_duplicate_username(self, client, test_user):
        """注册 - 用户名重复"""
        response = await client.post("/api/auth/register", json={
            "email": "another@example.com",
            "username": "testuser",  # 已存在
            "password": "MyPass123",
        })
        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "USERNAME_ALREADY_TAKEN"

    async def test_register_weak_password(self, client):
        """注册 - 密码强度不够"""
        response = await client.post("/api/auth/register", json={
            "email": "weak@example.com",
            "username": "weakuser",
            "password": "weakpass",  # 无大写字母和数字
        })
        assert response.status_code == 422

    async def test_register_team_without_name(self, client):
        """注册 - 团队注册未提供 team_name"""
        response = await client.post("/api/auth/register", json={
            "email": "team2@example.com",
            "username": "teamuser2",
            "password": "MyPass123",
            "account_type": "team",
            # 缺少 team_name
        })
        assert response.status_code == 422

    async def test_register_invalid_email(self, client):
        """注册 - 无效邮箱格式"""
        response = await client.post("/api/auth/register", json={
            "email": "not-an-email",
            "username": "user1",
            "password": "MyPass123",
        })
        assert response.status_code == 422

    async def test_register_invalid_username(self, client):
        """注册 - 用户名包含非法字符"""
        response = await client.post("/api/auth/register", json={
            "email": "user@example.com",
            "username": "user@name!",
            "password": "MyPass123",
        })
        assert response.status_code == 422
```

### 15.3 登录接口测试 `tests/test_auth_login.py`

```python
import pytest


@pytest.mark.asyncio
class TestLogin:
    """登录接口测试"""

    async def test_login_success(self, client, test_user):
        """登录 - 正常流程"""
        response = await client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "TestPass123",
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"

    async def test_login_wrong_password(self, client, test_user):
        """登录 - 密码错误"""
        response = await client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "WrongPass123",
        })
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "INVALID_CREDENTIALS"

    async def test_login_nonexistent_email(self, client):
        """登录 - 邮箱不存在"""
        response = await client.post("/api/auth/login", json={
            "email": "nobody@example.com",
            "password": "TestPass123",
        })
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "INVALID_CREDENTIALS"

    async def test_login_disabled_account(self, client, db_session, test_user):
        """登录 - 账号已禁用"""
        test_user.is_active = False
        await db_session.commit()

        response = await client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "TestPass123",
        })
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "ACCOUNT_DISABLED"
```

### 15.4 Token 刷新测试 `tests/test_auth_refresh.py`

```python
import pytest
from app.core.security import create_refresh_token


@pytest.mark.asyncio
class TestRefresh:
    """Token 刷新测试"""

    async def test_refresh_success(self, client, test_user):
        """刷新 - 正常流程"""
        refresh_token = create_refresh_token(
            user_id=str(test_user.id),
            email=test_user.email,
            account_type=test_user.account_type,
            team_id=None,
            username=test_user.username,
        )
        response = await client.post("/api/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data["data"]

    async def test_refresh_with_access_token(self, client, auth_headers):
        """刷新 - 使用 access_token 应失败"""
        token = auth_headers["Authorization"].replace("Bearer ", "")
        response = await client.post("/api/auth/refresh", json={
            "refresh_token": token,
        })
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "INVALID_TOKEN_TYPE"

    async def test_refresh_invalid_token(self, client):
        """刷新 - 无效 token"""
        response = await client.post("/api/auth/refresh", json={
            "refresh_token": "invalid.token.here",
        })
        assert response.status_code == 401
```

### 15.5 用户资料测试 `tests/test_users.py`

```python
import pytest


@pytest.mark.asyncio
class TestUsers:
    """用户资料测试"""

    async def test_get_me_success(self, client, auth_headers):
        """获取个人信息 - 正常"""
        response = await client.get("/api/users/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["email"] == "test@example.com"
        assert data["data"]["username"] == "testuser"

    async def test_get_me_unauthorized(self, client):
        """获取个人信息 - 未登录"""
        response = await client.get("/api/users/me")
        assert response.status_code == 401

    async def test_update_username_success(self, client, auth_headers):
        """修改用户名 - 正常"""
        response = await client.patch("/api/users/me", json={
            "username": "newname",
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["username"] == "newname"

    async def test_update_username_duplicate(self, client, auth_headers, db_session):
        """修改用户名 - 重复"""
        from app.models.user import User
        from app.core.security import hash_password
        other = User(
            email="other@example.com",
            username="taken",
            password_hash=hash_password("Pass1234"),
        )
        db_session.add(other)
        await db_session.commit()

        response = await client.patch("/api/users/me", json={
            "username": "taken",
        }, headers=auth_headers)
        assert response.status_code == 409

    async def test_update_no_fields(self, client, auth_headers):
        """修改 - 未提供任何字段"""
        response = await client.patch("/api/users/me", json={}, headers=auth_headers)
        assert response.status_code == 400

    async def test_change_password_success(self, client, auth_headers):
        """修改密码 - 正常"""
        response = await client.post("/api/users/me/change-password", json={
            "old_password": "TestPass123",
            "new_password": "NewPass456",
        }, headers=auth_headers)
        assert response.status_code == 200

    async def test_change_password_wrong_old(self, client, auth_headers):
        """修改密码 - 旧密码错误"""
        response = await client.post("/api/users/me/change-password", json={
            "old_password": "WrongOld123",
            "new_password": "NewPass456",
        }, headers=auth_headers)
        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "INVALID_OLD_PASSWORD"

    async def test_change_password_same(self, client, auth_headers):
        """修改密码 - 新旧密码相同"""
        response = await client.post("/api/users/me/change-password", json={
            "old_password": "TestPass123",
            "new_password": "TestPass123",
        }, headers=auth_headers)
        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "SAME_PASSWORD"
```

### 15.6 团队管理测试 `tests/test_teams.py`

```python
import pytest


@pytest.mark.asyncio
class TestTeams:
    """团队管理测试"""

    async def test_create_team_success(self, client, auth_headers):
        """创建团队 - 正常"""
        response = await client.post("/api/teams", json={
            "name": "My New Team",
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["team"]["name"] == "My New Team"
        assert len(data["data"]["team"]["invite_code"]) == 6
        assert data["data"]["user"]["account_type"] == "team"

    async def test_create_team_already_has_team(self, client, owner_headers):
        """创建团队 - 已有团队"""
        response = await client.post("/api/teams", json={
            "name": "Another Team",
        }, headers=owner_headers)
        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "ALREADY_HAS_TEAM"

    async def test_join_team_success(self, client, db_session):
        """加入团队 - 正常"""
        from app.models.user import User
        from app.core.security import hash_password, create_access_token

        user = User(
            email="joiner@example.com",
            username="joiner",
            password_hash=hash_password("TestPass123"),
            account_type="personal",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(
            user_id=str(user.id),
            email=user.email,
            account_type="personal",
            team_id=None,
            username="joiner",
        )
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post("/api/teams/join", json={
            "invite_code": "ABC123",
        }, headers=headers)
        assert response.status_code == 200

    async def test_join_team_invalid_code(self, client, auth_headers):
        """加入团队 - 无效邀请码"""
        response = await client.post("/api/teams/join", json={
            "invite_code": "ZZZZZZ",
        }, headers=auth_headers)
        assert response.status_code == 404

    async def test_get_members_as_owner(self, client, owner_headers):
        """获取成员列表 - owner 操作"""
        response = await client.get("/api/teams/members", headers=owner_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total"] >= 1

    async def test_get_members_as_member_forbidden(self, client, auth_headers):
        """获取成员列表 - 普通成员无权限"""
        response = await client.get("/api/teams/members", headers=auth_headers)
        # 如果该用户不是 owner，应返回 403
        assert response.status_code == 403

    async def test_reset_invite_code(self, client, owner_headers):
        """重置邀请码 - 正常"""
        response = await client.post("/api/teams/invite-code/reset", headers=owner_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]["invite_code"]) == 6

    async def test_delete_team(self, client, owner_headers):
        """删除团队 - 正常"""
        response = await client.delete("/api/teams", headers=owner_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["message"] == "团队已删除"
```

---

## 16. 给 Cursor 的额外说明

### 16.1 代码生成顺序

**严格按以下顺序生成代码**：

1. **配置变更**
   - 修改 `app/core/config.py`（新增 Phase 1 字段）
   - 修改 `.env.example`（新增配置项）

2. **枚举与模型**
   - 修改 `app/models/enums.py`（新增 AccountType）
   - 修改 `app/models/user.py`（扩展字段）
   - 新建 `app/models/team.py`（Team 模型）
   - 修改 `app/models/__init__.py`（导出 Team）

3. **安全工具扩展**
   - 修改 `app/core/security.py`（密码策略、JWT 生成、邀请码、黑名单）

4. **Schema 定义**
   - 新建 `app/schemas/auth.py`
   - 修改 `app/schemas/user.py`
   - 新建 `app/schemas/team.py`

5. **权限依赖**
   - 修改 `app/api/deps.py`（扩展 get_current_user、新增 require_owner）

6. **服务层**
   - 新建 `app/services/__init__.py`
   - 新建 `app/services/auth_service.py`
   - 新建 `app/services/user_service.py`
   - 新建 `app/services/team_service.py`

7. **路由层**
   - 新建 `app/api/v1/auth.py`
   - 修改 `app/api/v1/users.py`（从骨架到完整实现）
   - 新建 `app/api/v1/teams.py`
   - 修改 `app/api/router.py`（注册新路由）

8. **数据库迁移**
   ```bash
   alembic revision --autogenerate -m "phase1_user_system"
   alembic upgrade head
   ```

9. **测试**
   - 修改 `tests/conftest.py`（新增 fixtures）
   - 新建各测试文件

### 16.2 关键约束

- **所有 UUID 主键**由 Python 端 `uuid.uuid4()` 生成，不使用数据库端默认值
- **所有时间戳**使用 UTC 时区
- **密码 hash** 使用 bcrypt，rounds 从 config 读取（默认 12）
- **API 响应中绝不返回** `password_hash` 字段
- **登录失败**统一返回 `INVALID_CREDENTIALS`，不区分"用户不存在"和"密码错误"
- **Token 黑名单**的 Redis key 使用 `token_blacklist:{sha256(token)}` 格式
- **邀请码**字符集排除 `0, O, 1, I, L` 避免混淆
- **团队注册**必须提供 `team_name`，个人注册不需要
- **所有 API 路径前缀**为 `/api`（如 `/api/auth/register`）

### 16.3 命名规范

- 文件名：下划线分隔（`auth_service.py`、`team_service.py`）
- 类名：PascalCase（`AuthService`、`TeamService`、`RegisterRequest`）
- 函数名：snake_case（`create_access_token`、`generate_invite_code`）
- 错误码：UPPER_SNAKE_CASE（`EMAIL_ALREADY_REGISTERED`）
- 数据库表名：复数下划线（`users`、`teams`）

### 16.4 架构说明

- **路由层**（`api/v1/`）：仅负责请求解析、参数校验、调用服务层、组装响应
- **服务层**（`services/`）：包含所有业务逻辑，可独立测试
- **依赖层**（`api/deps.py`）：FastAPI 依赖注入，处理认证和权限校验
- **模型层**（`models/`）：SQLAlchemy ORM 定义
- **Schema 层**（`schemas/`）：Pydantic 请求/响应定义

### 16.5 Phase 1 完成验证清单

完成所有代码后，逐项验证：

- [ ] `POST /api/auth/register` 个人注册成功，返回 token
- [ ] `POST /api/auth/register` 团队注册成功，创建 team 记录，生成邀请码
- [ ] `POST /api/auth/login` 登录成功，返回 token
- [ ] `POST /api/auth/login` 错误密码返回 401 INVALID_CREDENTIALS
- [ ] `POST /api/auth/refresh` 用 refresh_token 换取新 access_token
- [ ] `POST /api/auth/logout` 后，原 token 不能再使用
- [ ] `GET /api/users/me` 返回完整用户信息（含团队信息）
- [ ] `PATCH /api/users/me` 修改用户名成功
- [ ] `POST /api/users/me/change-password` 修改密码成功
- [ ] `POST /api/teams` 个人用户创建团队成功
- [ ] `POST /api/teams/join` 通过邀请码加入团队
- [ ] `GET /api/teams/members` owner 获取成员列表
- [ ] `DELETE /api/teams/members/{user_id}` owner 移除成员
- [ ] `POST /api/teams/invite-code/reset` owner 重置邀请码
- [ ] `DELETE /api/teams` owner 删除团队，成员回退为个人
- [ ] 所有需要登录的接口，无 token 时返回 401
- [ ] 所有 owner 接口，非 owner 访问时返回 403
- [ ] pytest 全部通过

---

## 17. API 路由总表

| 方法 | 路径 | 描述 | 权限 | 请求体 | 响应关键字段 |
|------|------|------|------|--------|-------------|
| POST | `/api/auth/register` | 注册 | 公开 | RegisterRequest | user, team?, access_token, refresh_token |
| POST | `/api/auth/login` | 登录 | 公开 | LoginRequest | user, access_token, refresh_token |
| POST | `/api/auth/refresh` | 刷新 Token | 携带 refresh_token | RefreshRequest | access_token, expires_in |
| POST | `/api/auth/logout` | 登出 | 需要登录 | 无 | message |
| GET | `/api/users/me` | 获取当前用户 | 需要登录 | 无 | 完整用户资料（含团队） |
| PATCH | `/api/users/me` | 更新用户信息 | 需要登录 | UserUpdateRequest | 更新后的用户资料 |
| POST | `/api/users/me/change-password` | 修改密码 | 需要登录 | ChangePasswordRequest | message |
| POST | `/api/teams` | 创建团队 | 需要登录（个人用户） | TeamCreateRequest | team, user |
| POST | `/api/teams/join` | 加入团队 | 需要登录（个人用户） | JoinTeamRequest | team, user |
| GET | `/api/teams/members` | 获取成员列表 | 需要登录 + Owner | 无 | members[], total |
| DELETE | `/api/teams/members/{user_id}` | 移除成员 | 需要登录 + Owner | 无 | message |
| POST | `/api/teams/invite-code/reset` | 重置邀请码 | 需要登录 + Owner | 无 | invite_code |
| DELETE | `/api/teams` | 删除团队 | 需要登录 + Owner | 无 | message, affected_members |

---

## 附录 A：Redis Key 规范

| Key 模式 | 类型 | TTL | 说明 |
|----------|------|-----|------|
| `token_blacklist:{token_sha256}` | STRING | Token 剩余有效时间 | 登出后的 token 黑名单 |

## 附录 B：响应格式示例

### 成功响应

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "user@example.com",
      "username": "testuser",
      "avatar_url": null,
      "account_type": "personal",
      "team_id": null,
      "is_active": true,
      "created_at": "2026-07-14T10:00:00Z",
      "updated_at": "2026-07-14T10:00:00Z"
    },
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer"
  }
}
```

### 错误响应

```json
{
  "error": {
    "code": "EMAIL_ALREADY_REGISTERED",
    "message": "该邮箱已被注册",
    "details": []
  }
}
```

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
