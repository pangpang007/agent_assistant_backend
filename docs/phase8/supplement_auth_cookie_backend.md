---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 4263223131904378_0-data_volume/7650412177643372840-files/所有对话/主对话/supplement_auth_cookie_backend.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 4263223131904378#1784180792983
    ReservedCode2: ""
---
# Supplement: Cookie-based JWT 认证与自动续期方案（后端）

> **文档编号**: SUPPLEMENT-008  
> **版本**: v1.0  
> **日期**: 2025-07  
> **模块**: auth / middleware / config  
> **优先级**: P0（安全 + 体验核心改造）  
> **目标读者**: Cursor（AI 编码助手）  

---

## 1. 目标

| 维度 | 当前状态 | 目标状态 |
|------|----------|----------|
| Token 存储位置 | 前端 localStorage | 后端 HTTP-only Cookie |
| Token 续期 | 无自动续期，过期即强制登出 | 自动无感续期，用户全程无感 |
| Cookie 安全属性 | 无 | HttpOnly + Secure + SameSite=Lax |
| Token 泄露风险 | 高（XSS 可读取 localStorage） | 低（HttpOnly 阻止 JS 读取） |
| 登出体验 | 随机 JWT 过期导致突然登出 | 可预期的登出，续期机制避免意外过期 |

**核心原则**：前端零感知续期，后端全权管理 Token 生命周期。

---

## 2. 改动清单（总览）

| 序号 | 改动项 | 文件 / 模块 | 类型 |
|------|--------|-------------|------|
| 1 | 新增 Cookie 设置 / 清除工具函数 | `app/core/cookies.py` | 新增 |
| 2 | 新增 Redis Token 黑名单服务 | `app/services/token_blacklist.py` | 新增 |
| 3 | 新增认证中间件 | `app/middleware/auth.py` | 新增 |
| 4 | JWT 工具扩展（jti 生成、payload 结构变更） | `app/core/security.py` | 修改 |
| 5 | 登录 / 注册 / 登出 / 刷新路由重写 | `app/api/v1/auth.py` | 修改 |
| 6 | 新增 token-status 接口 | `app/api/v1/auth.py` | 新增 |
| 7 | CORS 配置更新 | `app/main.py` + `.env` | 修改 |
| 8 | 新增环境变量 | `.env` + `app/core/config.py` | 修改 |
| 9 | 兼容 Authorization header（过渡期） | `app/core/security.py` | 修改 |
| 10 | 错误码新增 | `app/core/errors.py` | 修改 |
| 11 | 依赖注入更新 | `app/api/deps.py` | 修改 |
| 12 | 测试用例 | `tests/test_auth_cookie.py` | 新增 |

---

## 3. Cookie 认证方案

### 3.1 Cookie 定义

| 属性 | 值 | 说明 |
|------|-----|------|
| Name | `access_token` | Access Token |
| Name | `refresh_token` | Refresh Token |
| HttpOnly | `True` | 禁止 JS 读取，防御 XSS |
| Secure | 生产 `True` / 开发 `False` | 仅 HTTPS 传输 |
| SameSite | `"lax"` | 防御 CSRF |
| Path | `"/"` | 全局有效 |
| Domain | 不设置或按配置 | 不设置时默认当前域名 |
| Max-Age | 与 JWT 有效期一致 | access_token: 30 min; refresh_token: 7 days |

### 3.2 工具函数 `app/core/cookies.py`

```python
from fastapi import Response
from app.core.config import settings


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
) -> None:
    """
    在响应中设置 access_token 和 refresh_token 的 HTTP-only Cookie。

    Args:
        response: FastAPI Response 对象
        access_token: 签名后的 JWT access token 字符串
        refresh_token: 签名后的 JWT refresh token 字符串
    """
    is_production = settings.ENVIRONMENT == "production"

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_production,          # 生产环境 HTTPS Only
        samesite="lax",
        path="/",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=is_production,
        samesite="lax",
        path="/",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )


def clear_auth_cookies(response: Response) -> None:
    """
    清除所有认证相关 Cookie（登出时调用）。
    """
    response.delete_cookie(
        key="access_token",
        path="/",
        samesite="lax",
    )
    response.delete_cookie(
        key="refresh_token",
        path="/",
        samesite="lax",
    )
```

### 3.3 使用场景一览

| 场景 | 调用函数 | 触发时机 |
|------|----------|----------|
| 登录成功 | `set_auth_cookies()` | `POST /api/auth/login` 返回 200 前 |
| 注册成功 | `set_auth_cookies()` | `POST /api/auth/register` 返回 201 前 |
| Token 自动续期 | `set_auth_cookies()` | 中间件检测到即将过期时 |
| 手动刷新 | `set_auth_cookies()` | `POST /api/auth/refresh` |
| 登出 | `clear_auth_cookies()` | `POST /api/auth/logout` |

---

## 4. JWT Payload 结构变更

### 4.1 新 Payload 结构

```json
{
  "sub": "user_id_123",
  "jti": "uuid-v4-random",
  "iat": 1700000000,
  "exp": 1700001800,
  "token_type": "access",
  "refresh_jti": "uuid-v4-random-for-refresh"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `sub` | string | 用户 ID（字符串形式） |
| `jti` | string | **新增** — JWT 唯一标识，用于黑名单。使用 `uuid4()` 生成 |
| `iat` | int | 签发时间（Unix timestamp） |
| `exp` | int | 过期时间（Unix timestamp） |
| `token_type` | string | `"access"` 或 `"refresh"`，区分 token 类型 |
| `refresh_jti` | string | **新增** — 对应 refresh token 的 jti，续期时用于同步刷新黑名单 |

### 4.2 `app/core/security.py` 改动

```python
import uuid
from datetime import datetime, timedelta, timezone
from jose import jwt
from app.core.config import settings


def create_access_token(
    user_id: str,
    expires_minutes: int = None,
) -> tuple[str, dict]:
    """
    创建 access token。

    Returns:
        tuple: (encoded_token, payload_dict)
        payload_dict 用于后续获取 jti 和 exp 信息。
    """
    if expires_minutes is None:
        expires_minutes = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
        "token_type": "access",
    }
    encoded = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded, payload


def create_refresh_token(
    user_id: str,
    expires_days: int = None,
) -> tuple[str, dict]:
    """
    创建 refresh token（有效期更长）。

    Returns:
        tuple: (encoded_token, payload_dict)
    """
    if expires_days is None:
        expires_days = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=expires_days)).timestamp()),
        "token_type": "refresh",
    }
    encoded = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded, payload


def decode_token(token: str) -> dict:
    """
    解码并验证 JWT token。

    Raises:
        jose.ExpiredSignatureError: token 已过期
        jose.JWTError: token 无效（签名错误、格式错误等）
    """
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    return payload
```

### 4.3 关键设计说明

- **为什么需要 `jti`**：JWT 是无状态的，无法在服务端主动使其失效。`jti` + Redis 黑名单是唯一可靠的主动失效方案。
- **为什么每次续期都生成新 `jti`**：确保每次续期产生一个全新的 token，旧 token 的 jti 被加入黑名单后无法再次使用，防止 token 重放。
- **`decode_token` 不检查黑名单**：黑名单检查在中间件层完成，`decode_token` 仅负责密码学验证，保持单一职责。

---

## 5. Redis Token 黑名单

### 5.1 设计

```
Key 格式:  token_blacklist:{jti}
Value:     "1"（字符串，仅表示存在即可）
TTL:       token 的剩余有效期（即 exp - current_time，秒）
```

### 5.2 为什么 TTL 是剩余有效期

- Token 过期后自然失效，黑名单中保留已过期 token 的 jti 没有意义。
- 设置 TTL 等于剩余有效期，可以让 Redis 自动清理过期条目，避免内存泄漏。

### 5.3 `app/services/token_blacklist.py`

```python
import time
import logging
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)


class TokenBlacklistService:
    """
    Token 黑名单服务 —— 基于 Redis，用于主动使 JWT 失效。
    """

    PREFIX = "token_blacklist"

    @classmethod
    async def blacklist(cls, jti: str, exp: int) -> None:
        """
        将 token 加入黑名单。

        Args:
            jti: JWT 的唯一标识
            exp: token 的过期时间（Unix timestamp）

        TTL 计算: max(exp - now, 1)，最少保留 1 秒
        """
        now = int(time.time())
        ttl = max(exp - now, 1)

        redis = await get_redis_client()
        key = f"{cls.PREFIX}:{jti}"
        await redis.set(key, "1", ex=ttl)
        logger.info(f"Token blacklisted: jti={jti}, ttl={ttl}s")

    @classmethod
    async def is_blacklisted(cls, jti: str) -> bool:
        """
        检查 token 是否在黑名单中。

        Args:
            jti: JWT 的唯一标识

        Returns:
            True 表示已被黑名单（token 无效）
        """
        redis = await get_redis_client()
        key = f"{cls.PREFIX}:{jti}"
        value = await redis.get(key)
        return value is not None

    @classmethod
    async def remove(cls, jti: str) -> None:
        """
        从黑名单中移除（极少使用，仅在需要撤销登出时）。

        Args:
            jti: JWT 的唯一标识
        """
        redis = await get_redis_client()
        key = f"{cls.PREFIX}:{jti}"
        await redis.delete(key)
        logger.info(f"Token removed from blacklist: jti={jti}")
```

### 5.4 Redis 连接说明

- `get_redis_client()` 复用项目已有的 Redis 连接池（`app/core/redis.py`）。
- 黑名单操作使用异步 Redis 客户端（`redis.asyncio`）。
- 如果 Redis 不可用：
  - **写入失败**（`blacklist`）：记录 warning 日志，**不阻断请求**。黑名单写入是增强安全措施，不应因 Redis 故障影响正常功能。
  - **读取失败**（`is_blacklisted`）：记录 error 日志，**视为 token 不在黑名单**（放行）。这是一个降级策略：宁可放行已登出的 token（等其自然过期），也不要因 Redis 故障导致所有用户无法访问。

### 5.5 黑名单的生命周期

```
登录 → 生成 access_token（jti=A）+ refresh_token（jti=B）
  ↓
正常使用 → 中间件每次检查 jti=A 是否在黑名单
  ↓
自动续期 → 生成新 access_token（jti=C）+ 新 refresh_token（jti=D）
         → 将 jti=A 加入黑名单（TTL = 旧 token 剩余有效期）
         → 将 jti=B 加入黑名单（TTL = 旧 refresh_token 剩余有效期）
  ↓
登出 → 将当前 jti 加入黑名单（TTL = 剩余有效期）→ 清除 Cookie
```

---

## 6. 认证中间件

### 6.1 文件：`app/middleware/auth.py`

### 6.2 完整流程

```
请求进入
  │
  ├─ 路径是否在白名单？（/api/auth/login, /api/auth/register, /docs, /openapi.json 等）
  │    └─ 是 → 直接放行，不做任何处理
  │
  ├─ 从 Cookie 中读取 access_token
  │    └─ Cookie 不存在 → 检查 Authorization header（兼容模式）
  │         └─ Header 也不存在 → 返回 401 COOKIE_MISSING
  │         └─ Header 存在 → 使用 header 中的 token（打印 deprecation warning）
  │
  ├─ decode_token（验证签名、过期时间）
  │    └─ ExpiredSignatureError → 尝试用 refresh_token 恢复
  │         ├─ Cookie 中有 refresh_token → 验证 refresh_token
  │         │    ├─ 有效 → 自动刷新，生成新 token 对，设 Cookie，放行（本次请求继续）
  │         │    └─ 无效/过期 → 返回 401 TOKEN_EXPIRED
  │         └─ 无 refresh_token → 返回 401 TOKEN_EXPIRED
  │
  │    └─ JWTError → 返回 401（token 无效）
  │
  ├─ 检查 token_type == "access"
  │    └─ 不是 → 返回 401（不能用 refresh_token 当 access_token）
  │
  ├─ 检查黑名单: is_blacklisted(jti)
  │    └─ 在黑名单中 → 返回 401 TOKEN_BLACKLISTED
  │
  ├─ 检查是否需要自动续期
  │    └─ exp - now < threshold（默认 10 分钟）
  │         └─ 是 → 生成新 access_token + 新 refresh_token
  │              → 将旧 access_token 的 jti 加入黑名单
  │              → 将旧 refresh_token 的 jti 加入黑名单（如果存在）
  │              → 在 response 上 set_cookie（新 token）
  │              → 记录日志: "Auto-refreshed token for user {user_id}"
  │
  └─ 将 user_id 注入 request.state.user_id → 放行
```

### 6.3 代码实现

```python
import time
import logging
import warnings
from typing import Optional
from jose import ExpiredSignatureError, JWTError
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.security import decode_token, create_access_token, create_refresh_token
from app.core.cookies import set_auth_cookies
from app.services.token_blacklist import TokenBlacklistService

logger = logging.getLogger(__name__)

# 不需要认证的路径白名单
PUBLIC_PATHS = {
    "/api/auth/login",
    "/api/auth/register",
    "/docs",
    "/docs/oauth2-redirect",
    "/openapi.json",
    "/redoc",
    "/health",
    "/api/health",
}

# 前缀匹配白名单（用于 Swagger UI 静态资源等）
PUBLIC_PATH_PREFIXES = (
    "/docs",
    "/redoc",
    "/static",
)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    JWT Cookie 认证中间件。

    职责：
    1. 从 Cookie / Header 中提取 token
    2. 验证 token 有效性 + 黑名单检查
    3. 自动无感续期（剩余有效期 < threshold 时）
    4. 将 user_id 注入 request.state
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # ── Step 0: 白名单放行 ──
        if self._is_public_path(request.url.path):
            return await call_next(request)

        # ── Step 1: 提取 token ──
        token, source = self._extract_token(request)
        if token is None:
            return JSONResponse(
                status_code=401,
                content={"error": "COOKIE_MISSING", "message": "缺少认证 cookie"},
            )

        # ── Step 2: 解码 token ──
        try:
            payload = decode_token(token)
        except ExpiredSignatureError:
            # access_token 过期 → 尝试用 refresh_token 恢复
            response = await self._try_refresh_on_expired(request)
            if response:
                return response
            return JSONResponse(
                status_code=401,
                content={"error": "TOKEN_EXPIRED", "message": "Token 已过期，请重新登录"},
            )
        except JWTError as e:
            return JSONResponse(
                status_code=401,
                content={"error": "TOKEN_INVALID", "message": f"Token 无效: {str(e)}"},
            )

        # ── Step 3: 校验 token_type ──
        if payload.get("token_type") != "access":
            return JSONResponse(
                status_code=401,
                content={"error": "TOKEN_INVALID", "message": "Token 类型错误"},
            )

        # ── Step 4: 黑名单检查 ──
        jti = payload.get("jti")
        if jti and await TokenBlacklistService.is_blacklisted(jti):
            return JSONResponse(
                status_code=401,
                content={"error": "TOKEN_BLACKLISTED", "message": "Token 已被吊销"},
            )

        # ── Step 5: 注入 user_id ──
        request.state.user_id = payload["sub"]

        # ── Step 6: 处理后续请求 ──
        response = await call_next(request)

        # ── Step 7: 检查是否需要自动续期（在响应阶段处理） ──
        await self._maybe_auto_refresh(request, response, payload)

        return response

    def _is_public_path(self, path: str) -> bool:
        """检查路径是否在白名单中"""
        if path in PUBLIC_PATHS:
            return True
        return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)

    def _extract_token(self, request: Request) -> tuple[Optional[str], str]:
        """
        从请求中提取 token。

        优先级：Cookie > Authorization Header（兼容模式）

        Returns:
            tuple: (token_string, source)
            source: "cookie" | "header" | None
        """
        # 优先从 Cookie 读取
        cookie_token = request.cookies.get("access_token")
        if cookie_token:
            return cookie_token, "cookie"

        # Fallback: 从 Authorization header 读取（过渡期兼容）
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            header_token = auth_header[7:]  # 去掉 "Bearer " 前缀
            warnings.warn(
                "Authorization header 方式将在下个版本废弃，"
                "请迁移到 Cookie 认证方式。"
                f"Path: {request.url.path}",
                DeprecationWarning,
                stacklevel=2,
            )
            logger.warning(
                f"DEPRECATION: Authorization header used for {request.url.path}. "
                "Please migrate to Cookie-based auth."
            )
            return header_token, "header"

        return None, None

    async def _try_refresh_on_expired(
        self, request: Request
    ) -> Optional[Response]:
        """
        access_token 过期后，尝试用 refresh_token 恢复会话。

        Returns:
            Response（带新 Cookie 的 401 响应），或 None（refresh 也失败）
        """
        refresh_token = request.cookies.get("refresh_token")
        if not refresh_token:
            return None

        try:
            refresh_payload = decode_token(refresh_token)
        except (ExpiredSignatureError, JWTError):
            return None

        if refresh_payload.get("token_type") != "refresh":
            return None

        # 检查 refresh token 是否在黑名单
        refresh_jti = refresh_payload.get("jti")
        if refresh_jti and await TokenBlacklistService.is_blacklisted(refresh_jti):
            return None

        # refresh_token 有效 → 生成新的 token 对
        user_id = refresh_payload["sub"]

        new_access_token, new_access_payload = create_access_token(user_id)
        new_refresh_token, new_refresh_payload = create_refresh_token(user_id)

        # 将旧 refresh_token 加入黑名单
        if refresh_jti:
            await TokenBlacklistService.blacklist(
                refresh_jti, refresh_payload["exp"]
            )

        # 构建响应（返回 401 让前端知道 token 过期了，但附带新 cookie）
        # 实际上对于自动续期场景，我们不应该返回 401
        # 而是应该生成新 token 后继续处理请求
        # 这里的设计是：中间件返回一个特殊的 response，
        # 让请求继续（需要重新构造 request 并重新调用 call_next）
        # 
        # 但由于 Starlette middleware 的限制，更好的做法是：
        # 在 refresh 成功后，将新 token 设置到 request 上，继续处理
        # 
        # 实际实现方案：返回 None，让上层处理
        # 在 dispatch 中，如果 _try_refresh_on_expired 返回的不是 JSONResponse
        # 而是一个标记，则用新 token 重新处理
        
        # 简化方案：这里直接生成新 token，存入 request.state 供后续使用
        request.state._refreshed_access_token = new_access_token[7:]  # 去掉可能的编码
        request.state._refreshed_access_payload = new_access_payload
        request.state._refreshed_refresh_token = new_refresh_token
        request.state._needs_cookie_refresh = True
        request.state.user_id = user_id
        
        return None  # 表示 refresh 成功，继续处理

    async def _maybe_auto_refresh(
        self, request: Request, response: Response, payload: dict
    ) -> None:
        """
        检查 token 是否需要自动续期。
        在 call_next 之后调用，直接修改 response 的 Set-Cookie header。
        """
        # 处理 refresh_on_expired 的情况
        if getattr(request.state, "_needs_cookie_refresh", False):
            set_auth_cookies(
                response,
                request.state._refreshed_access_token,
                request.state._refreshed_refresh_token,
            )
            return

        exp = payload.get("exp", 0)
        now = int(time.time())
        remaining = exp - now
        threshold = settings.JWT_AUTO_REFRESH_THRESHOLD_MINUTES * 60

        if remaining < threshold:
            user_id = payload["sub"]
            old_jti = payload.get("jti")

            # 生成新 token 对
            new_access_token, new_access_payload = create_access_token(user_id)
            new_refresh_token, new_refresh_payload = create_refresh_token(user_id)

            # 将旧 token 加入黑名单
            if old_jti:
                await TokenBlacklistService.blacklist(old_jti, exp)

            # 处理旧 refresh_token（如果存在且未过期）
            old_refresh_token = request.cookies.get("refresh_token")
            if old_refresh_token:
                try:
                    old_refresh_payload = decode_token(old_refresh_token)
                    old_refresh_jti = old_refresh_payload.get("jti")
                    if old_refresh_jti:
                        await TokenBlacklistService.blacklist(
                            old_refresh_jti, old_refresh_payload["exp"]
                        )
                except JWTError:
                    pass  # 旧的 refresh token 可能已过期，忽略

            # 设置新 Cookie
            set_auth_cookies(response, new_access_token, new_refresh_token)

            logger.info(
                f"Auto-refreshed token for user {user_id}, "
                f"old_jti={old_jti}, remaining={remaining}s"
            )
```

### 6.4 中间件执行顺序

```
请求生命周期：

1. CORS Middleware（最外层）
   ↓
2. Auth Middleware（本中间件）
   ↓
3. 路由 / 依赖注入（内层）
```

**在 `app/main.py` 中的注册顺序**（Starlette 中间件是洋葱模型，后注册的先执行）：

```python
app.add_middleware(AuthMiddleware)      # 后注册 = 先执行（内层）
app.add_middleware(CORSMiddleware)      # 先注册 = 后执行（外层）
# 注意：实际上 Starlette 的 add_middleware 是倒序执行的
# 所以这里 CORSMiddleware 在外层，AuthMiddleware 在内层
```

**为什么 CORS 必须在外层**：
- 浏览器发送 preflight OPTIONS 请求时，需要 CORS middleware 先处理并返回正确的 CORS 头
- Auth middleware 不应该拦截 OPTIONS 请求（已在白名单逻辑中处理）

### 6.5 中间件对 OPTIONS 请求的处理

```python
# 在 dispatch 开头增加对 OPTIONS 请求的放行
if request.method == "OPTIONS":
    return await call_next(request)
```

---

## 7. 路由变更

### 7.1 `POST /api/auth/login`

**请求**：
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**响应**：
- HTTP 200
- Body:
  ```json
  {
    "user": {
      "id": "uuid-123",
      "email": "user@example.com",
      "nickname": "汤圆",
      "avatar_url": "https://..."
    }
  }
  ```
- **不再在 body 中返回 `access_token` 和 `refresh_token`**
- Headers:
  ```
  Set-Cookie: access_token=eyJ...; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=1800
  Set-Cookie: refresh_token=eyJ...; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=604800
  ```

**后端逻辑**：
```python
@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # 1. 验证用户身份（原有逻辑不变）
    user = await authenticate_user(payload.email, payload.password, db)
    if not user:
        raise AuthError("邮箱或密码错误")

    # 2. 生成 token 对
    access_token, access_payload = create_access_token(str(user.id))
    refresh_token, refresh_payload = create_refresh_token(str(user.id))

    # 3. 设置 Cookie
    set_auth_cookies(response, access_token, refresh_token)

    # 4. 返回用户信息（不含 token）
    return LoginResponse(user=UserInfo.from_orm(user))
```

### 7.2 `POST /api/auth/register`

**请求**：
```json
{
  "email": "user@example.com",
  "password": "password123",
  "nickname": "汤圆"
}
```

**响应**：
- HTTP 201
- Body:
  ```json
  {
    "user": {
      "id": "uuid-123",
      "email": "user@example.com",
      "nickname": "汤圆",
      "avatar_url": null
    }
  }
  ```
- Headers: 同 login（Set-Cookie）

**后端逻辑**：
```python
@router.post("/register", status_code=201, response_model=RegisterResponse)
async def register(
    payload: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # 1. 创建用户（原有逻辑不变）
    user = await create_user(payload, db)

    # 2. 生成 token 对
    access_token, _ = create_access_token(str(user.id))
    refresh_token, _ = create_refresh_token(str(user.id))

    # 3. 设置 Cookie
    set_auth_cookies(response, access_token, refresh_token)

    # 4. 返回用户信息
    return RegisterResponse(user=UserInfo.from_orm(user))
```

### 7.3 `POST /api/auth/logout`

**请求**：无需 body（token 从 Cookie 读取）

**响应**：
- HTTP 200
- Body:
  ```json
  {
    "message": "已成功登出"
  }
  ```
- Headers:
  ```
  Set-Cookie: access_token=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0
  Set-Cookie: refresh_token=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0
  ```

**后端逻辑**：
```python
@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
):
    # 1. 从 request.state 获取当前 token 信息
    # （中间件已经解析并验证过 token）
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")

    # 2. 将当前 token 加入黑名单
    if access_token:
        try:
            payload = decode_token(access_token)
            jti = payload.get("jti")
            if jti:
                await TokenBlacklistService.blacklist(jti, payload["exp"])
        except JWTError:
            pass  # token 已过期也允许登出

    if refresh_token:
        try:
            payload = decode_token(refresh_token)
            jti = payload.get("jti")
            if jti:
                await TokenBlacklistService.blacklist(jti, payload["exp"])
        except JWTError:
            pass

    # 3. 清除 Cookie
    clear_auth_cookies(response)

    return {"message": "已成功登出"}
```

### 7.4 `POST /api/auth/refresh`

**说明**：手动强制刷新接口，用于极端情况（如自动续期失败后的兜底）。

**请求**：无需 body（从 Cookie 读取 refresh_token）

**响应**：
- HTTP 200
- Body:
  ```json
  {
    "message": "Token 已刷新"
  }
  ```
- Headers:
  ```
  Set-Cookie: access_token=<new>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=1800
  Set-Cookie: refresh_token=<new>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=604800
  ```

**后端逻辑**：
```python
@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
):
    # 1. 读取 refresh_token
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise AuthError(code="COOKIE_MISSING", message="缺少 refresh_token cookie")

    # 2. 验证 refresh_token
    try:
        payload = decode_token(refresh_token)
    except ExpiredSignatureError:
        raise AuthError(code="TOKEN_EXPIRED", message="refresh_token 已过期，请重新登录")
    except JWTError:
        raise AuthError(code="TOKEN_INVALID", message="refresh_token 无效")

    if payload.get("token_type") != "refresh":
        raise AuthError(code="TOKEN_INVALID", message="Token 类型错误")

    # 3. 检查黑名单
    jti = payload.get("jti")
    if jti and await TokenBlacklistService.is_blacklisted(jti):
        raise AuthError(code="TOKEN_BLACKLISTED", message="Token 已被吊销")

    # 4. 将旧 token 加入黑名单
    if jti:
        await TokenBlacklistService.blacklist(jti, payload["exp"])

    # 同时黑名单旧的 access_token
    old_access_token = request.cookies.get("access_token")
    if old_access_token:
        try:
            old_payload = decode_token(old_access_token)
            old_jti = old_payload.get("jti")
            if old_jti:
                await TokenBlacklistService.blacklist(old_jti, old_payload["exp"])
        except JWTError:
            pass

    # 5. 生成新 token 对
    user_id = payload["sub"]
    new_access_token, _ = create_access_token(user_id)
    new_refresh_token, _ = create_refresh_token(user_id)

    # 6. 设置新 Cookie
    set_auth_cookies(response, new_access_token, new_refresh_token)

    return {"message": "Token 已刷新"}
```

### 7.5 `GET /api/auth/token-status`（新接口）

**说明**：供前端主动检查 token 状态，用于 UI 展示或调试。

**请求**：无（Cookie 自动附带）

**响应**：
- HTTP 200
- Body:
  ```json
  {
    "is_valid": true,
    "user_id": "uuid-123",
    "access_token_expires_at": 1700001800,
    "access_token_remaining_seconds": 1500,
    "access_token_needs_refresh": true,
    "refresh_token_valid": true,
    "refresh_token_expires_at": 1700604800
  }
  ```

**后端逻辑**：
```python
@router.get("/token-status")
async def token_status(request: Request):
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")
    now = int(time.time())

    result = {
        "is_valid": False,
        "user_id": None,
        "access_token_expires_at": None,
        "access_token_remaining_seconds": None,
        "access_token_needs_refresh": False,
        "refresh_token_valid": False,
        "refresh_token_expires_at": None,
    }

    # 检查 access_token
    if access_token:
        try:
            payload = decode_token(access_token)
            jti = payload.get("jti")
            is_blacklisted = jti and await TokenBlacklistService.is_blacklisted(jti)
            
            if not is_blacklisted:
                exp = payload["exp"]
                remaining = exp - now
                result.update({
                    "is_valid": True,
                    "user_id": payload["sub"],
                    "access_token_expires_at": exp,
                    "access_token_remaining_seconds": max(remaining, 0),
                    "access_token_needs_refresh": remaining < (
                        settings.JWT_AUTO_REFRESH_THRESHOLD_MINUTES * 60
                    ),
                })
        except JWTError:
            pass

    # 检查 refresh_token
    if refresh_token:
        try:
            payload = decode_token(refresh_token)
            jti = payload.get("jti")
            is_blacklisted = jti and await TokenBlacklistService.is_blacklisted(jti)
            if not is_blacklisted:
                result["refresh_token_valid"] = True
                result["refresh_token_expires_at"] = payload["exp"]
        except JWTError:
            pass

    return result
```

---

## 8. CORS 配置变更

### 8.1 问题

当前 CORS 配置使用 `allow_origins=["*"]`，这在启用 `allow_credentials=True` 时会被浏览器拒绝。
根据 CORS 规范，`Access-Control-Allow-Origin: *` 与 `Access-Control-Allow-Credentials: true` 不能同时使用。

### 8.2 改动

**`app/main.py`**：
```python
from app.core.config import settings

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,    # 从环境变量读取，不再使用 ["*"]
    allow_credentials=True,                  # 允许携带 Cookie
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],  # Authorization 过渡期保留
    expose_headers=["Set-Cookie"],           # 允许前端读取 Set-Cookie header（调试用）
)
```

**`app/core/config.py` 新增**：
```python
class Settings(BaseSettings):
    # ... 其他配置 ...
    
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",   # 开发环境
        "http://localhost:3000",   # 备选开发端口
    ]
    
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            # 支持逗号分隔的环境变量格式
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    
    # ... 新增 JWT 相关配置 ...
```

### 8.3 环境变量

```bash
# .env
CORS_ORIGINS=https://soupcircle.xyz,http://localhost:5173
```

### 8.4 注意事项

- **开发环境**：`http://localhost:5173`（Vite 默认端口）
- **生产环境**：`https://soupcircle.xyz`（必须带协议）
- **本地调试**：如果前端使用 `localhost`，后端也需要在 `localhost`，确保 origin 匹配
- **多环境**：可以配置多个 origin，如 `CORS_ORIGINS=https://app.example.com,https://staging.example.com`

---

## 9. 环境变量汇总

### 9.1 新增变量

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `CORS_ORIGINS` | string (逗号分隔) | `http://localhost:5173` | 允许的 CORS 域名列表 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | int | `30` | Access Token 有效期（分钟） |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | int | `7` | Refresh Token 有效期（天） |
| `JWT_AUTO_REFRESH_THRESHOLD_MINUTES` | int | `10` | 自动续期阈值：剩余有效期低于此值时触发续期（分钟） |
| `REDIS_TOKEN_BLACKLIST_PREFIX` | string | `token_blacklist` | Redis 黑名单 key 前缀 |
| `ENVIRONMENT` | string | `development` | 运行环境：`development` / `production` |

### 9.2 完整 `.env.example` 更新

```bash
# ── 认证 & 安全 ──
SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
JWT_AUTO_REFRESH_THRESHOLD_MINUTES=10

# ── CORS ──
CORS_ORIGINS=https://soupcircle.xyz,http://localhost:5173

# ── Redis ──
REDIS_URL=redis://localhost:6379/0
REDIS_TOKEN_BLACKLIST_PREFIX=token_blacklist

# ── 环境 ──
ENVIRONMENT=development
# ENVIRONMENT=production  # 生产环境切换
```

### 9.3 `app/core/config.py` 完整新增字段

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ── 环境 ──
    ENVIRONMENT: str = "development"

    # ── JWT ──
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_AUTO_REFRESH_THRESHOLD_MINUTES: int = 10

    # ── CORS ──
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # ── Redis 黑名单 ──
    REDIS_TOKEN_BLACKLIST_PREFIX: str = "token_blacklist"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"
```

---

## 10. 错误码

### 10.1 新增错误码

| 错误码 | HTTP Status | 含义 | 前端处理建议 |
|--------|-------------|------|-------------|
| `TOKEN_EXPIRED` | 401 | Token 已过期且无法自动续期 | 跳转到登录页 |
| `TOKEN_BLACKLISTED` | 401 | Token 已被加入黑名单（已在其他设备登出或已被吊销） | 跳转到登录页 |
| `COOKIE_MISSING` | 401 | 缺少认证 Cookie（用户未登录或 Cookie 被清除） | 跳转到登录页 |
| `TOKEN_INVALID` | 401 | Token 无效（签名错误、格式错误、类型错误） | 跳转到登录页 |

### 10.2 统一错误响应格式

```json
{
  "error": "TOKEN_EXPIRED",
  "message": "Token 已过期，请重新登录"
}
```

### 10.3 `app/core/errors.py` 新增

```python
class AuthError(Exception):
    """认证相关错误"""
    
    def __init__(self, code: str, message: str, status_code: int = 401):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# 预定义错误
TOKEN_EXPIRED = AuthError("TOKEN_EXPIRED", "Token 已过期，请重新登录")
TOKEN_BLACKLISTED = AuthError("TOKEN_BLACKLISTED", "Token 已被吊销")
COOKIE_MISSING = AuthError("COOKIE_MISSING", "缺少认证 cookie")
TOKEN_INVALID = AuthError("TOKEN_INVALID", "Token 无效")


# 全局异常处理器（在 main.py 中注册）
@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, exc: AuthError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
    )
```

---

## 11. 依赖注入更新

### 11.1 `app/api/deps.py`

**改动**：`get_current_user` 依赖不再需要自己解析 token（中间件已完成），直接从 `request.state` 获取。

```python
from fastapi import Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

async def get_current_user_id(request: Request) -> str:
    """
    从 request.state 获取当前用户 ID。
    由 AuthMiddleware 在请求处理前注入。
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise AuthError(code="COOKIE_MISSING", message="未认证")
    return user_id


async def get_current_user(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    获取当前登录用户对象。
    """
    user = await db.get(User, user_id)
    if not user:
        raise AuthError(code="TOKEN_INVALID", message="用户不存在")
    if not user.is_active:
        raise AuthError(code="TOKEN_INVALID", message="用户已被禁用")
    return user
```

### 11.2 变更说明

| 项目 | 旧版 | 新版 |
|------|------|------|
| Token 解析位置 | `get_current_user_id` 中手动解析 | `AuthMiddleware` 中统一解析 |
| Token 来源 | `Authorization` header | Cookie（优先） > Header（过渡期） |
| `request.state.user_id` | 不存在 | 中间件注入 |

---

## 12. 向后兼容策略

### 12.1 过渡期设计（1 个版本）

```
Phase A（当前版本）: Cookie 优先 + Header fallback
  - 中间件先检查 Cookie，没有时检查 Authorization header
  - 使用 header 时打印 deprecation warning
  - 登录/注册响应同时设置 Cookie 和返回 body 中的 token（可选）
  
Phase B（下个版本）: Cookie only
  - 移除 Authorization header 的 fallback 逻辑
  - 登录/注册响应不再在 body 中返回 token
  - 前端必须完全迁移到 Cookie 模式
```

### 12.2 兼容模式下的登录响应（Phase A）

```python
@router.post("/login")
async def login(payload: LoginRequest, response: Response, db=Depends(get_db)):
    user = await authenticate_user(payload.email, payload.password, db)
    
    access_token, _ = create_access_token(str(user.id))
    refresh_token, _ = create_refresh_token(str(user.id))
    
    # 设置 Cookie（新版前端使用）
    set_auth_cookies(response, access_token, refresh_token)
    
    # Phase A: 同时在 body 中返回 token（兼容旧版前端）
    # Phase B: 移除这两个字段
    return {
        "user": UserInfo.from_orm(user),
        "access_token": access_token,        # DEPRECATED: 将在下版本移除
        "refresh_token": refresh_token,       # DEPRECATED: 将在下版本移除
        "token_type": "bearer",               # DEPRECATED: 将在下版本移除
    }
```

### 12.3 前端迁移检测

```python
# 在日志中记录请求来源，帮助评估迁移进度
async def _log_auth_source(request: Request, source: str):
    if source == "header":
        logger.warning(
            f"AUTH_MIGRATION: Client using header auth for {request.url.path}. "
            f"User-Agent: {request.headers.get('user-agent', 'unknown')}"
        )
```

---

## 13. 数据模型变更

### 13.1 请求/响应 Schema 变更

```python
# app/schemas/auth.py

from pydantic import BaseModel, EmailStr
from typing import Optional
from app.schemas.user import UserResponse


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """
    Phase A: 包含 token 字段（向后兼容）
    Phase B: 移除 token 字段
    """
    user: UserResponse
    # Phase A 保留，Phase B 移除 ↓
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: Optional[str] = None


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    nickname: str


class RegisterResponse(BaseModel):
    user: UserResponse
    # Phase A 保留，Phase B 移除 ↓
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: Optional[str] = None


class TokenStatusResponse(BaseModel):
    is_valid: bool
    user_id: Optional[str] = None
    access_token_expires_at: Optional[int] = None
    access_token_remaining_seconds: Optional[int] = None
    access_token_needs_refresh: bool = False
    refresh_token_valid: bool = False
    refresh_token_expires_at: Optional[int] = None
```

---

## 14. 完整请求流程图

### 14.1 登录流程

```
前端                            后端
 │                               │
 │── POST /api/auth/login ──────>│
 │   { email, password }         │
 │                               │── 验证用户
 │                               │── 生成 access_token (jti=A, exp=now+30min)
 │                               │── 生成 refresh_token (jti=B, exp=now+7days)
 │                               │── Set-Cookie: access_token=...
 │                               │── Set-Cookie: refresh_token=...
 │<── 200 { user } ─────────────│
 │                               │
 │   [Cookie 已存储，后续请求自动附带]
```

### 14.2 普通请求（token 充足）

```
前端                            后端
 │                               │
 │── GET /api/posts ────────────>│
 │   Cookie: access_token=eyJ... │
 │                               │── AuthMiddleware:
 │                               │    1. 读取 Cookie access_token ✓
 │                               │    2. decode_token ✓
 │                               │    3. 黑名单检查 ✓（不在黑名单）
 │                               │    4. 剩余有效期 > 10min，不续期
 │                               │    5. request.state.user_id = "..."
 │                               │── 正常处理请求
 │<── 200 { posts } ────────────│
```

### 14.3 自动续期流程

```
前端                            后端
 │                               │
 │── GET /api/posts ────────────>│
 │   Cookie: access_token=eyJ... │
 │   (剩余有效期 8 分钟 < 10 分钟阈值)
 │                               │── AuthMiddleware:
 │                               │    1-4: 同上（验证通过）
 │                               │    5. 剩余有效期 < 10min → 触发续期
 │                               │    6. 生成新 access_token (jti=C)
 │                               │    7. 生成新 refresh_token (jti=D)
 │                               │    8. 黑名单 jti=A (TTL = 旧token剩余时间)
 │                               │    9. 黑名单 jti=B
 │<── 200 { posts } ────────────│
 │   Set-Cookie: access_token=<新>│
 │   Set-Cookie: refresh_token=<新>│
 │                               │
 │   [浏览器自动更新 Cookie，前端无感]
```

### 14.4 Token 过期 + Refresh Token 恢复

```
前端                            后端
 │                               │
 │── GET /api/posts ────────────>│
 │   Cookie: access_token=<过期>  │
 │   Cookie: refresh_token=<有效> │
 │                               │── AuthMiddleware:
 │                               │    1. decode_token → ExpiredSignatureError
 │                               │    2. 读取 Cookie refresh_token
 │                               │    3. decode refresh_token → 有效 ✓
 │                               │    4. 生成新 token 对
 │                               │    5. 黑名单旧 refresh_token
 │                               │    6. Set-Cookie 新 token
 │<── 200 { posts } ────────────│
 │   Set-Cookie: access_token=<新>│
 │   Set-Cookie: refresh_token=<新>│
 │   (请求正常完成，用户无感)
```

### 14.5 完全过期流程

```
前端                            后端
 │                               │
 │── GET /api/posts ────────────>│
 │   Cookie: access_token=<过期>  │
 │   Cookie: refresh_token=<过期> │
 │                               │── AuthMiddleware:
 │                               │    1. decode access_token → 过期
 │                               │    2. decode refresh_token → 也过期
 │<── 401 TOKEN_EXPIRED ────────│
 │                               │
 │   [前端收到 401 → 跳转登录页]
```

### 14.6 登出流程

```
前端                            后端
 │                               │
 │── POST /api/auth/logout ─────>│
 │   Cookie: access_token=eyJ... │
 │                               │── 从 Cookie 读取 token
 │                               │── decode token → 获取 jti
 │                               │── 黑名单 jti（TTL = 剩余有效期）
 │                               │── 黑名单 refresh_token jti
 │                               │── 清除 Cookie (Max-Age=0)
 │<── 200 { message } ──────────│
 │   Set-Cookie: access_token=; Max-Age=0
 │   Set-Cookie: refresh_token=; Max-Age=0
 │                               │
 │   [Cookie 已清除]
 │   [旧 token 即使被截获也无法使用（已在黑名单）]
```

---

## 15. 与 Phase 0-7 的衔接

### 15.1 影响范围

| Phase | 模块 | 影响 | 改动 |
|-------|------|------|------|
| Phase 0 | 项目骨架 | CORS 配置 | 修改 `main.py` 中 CORS 设置 |
| Phase 1 | 数据模型 | 无 | 无改动 |
| Phase 2 | 认证 | 核心改动 | 重写 auth 路由、security 模块、新增中间件 |
| Phase 3 | 内容 CRUD | 依赖注入变更 | `get_current_user` 改为从 `request.state` 读取 |
| Phase 4 | 评论 | 同 Phase 3 | 同上 |
| Phase 5 | 点赞/收藏 | 同 Phase 3 | 同上 |
| Phase 6 | 关注 | 同 Phase 3 | 同上 |
| Phase 7 | 搜索 | 无 | 无改动 |

### 15.2 迁移检查清单

- [ ] `app/main.py`：CORS 配置更新
- [ ] `app/core/config.py`：新增环境变量
- [ ] `app/core/security.py`：Token 创建/解码函数更新
- [ ] `app/core/cookies.py`：新增 Cookie 工具函数
- [ ] `app/core/redis.py`：确认 Redis 连接可用
- [ ] `app/core/errors.py`：新增 AuthError 及错误码
- [ ] `app/services/token_blacklist.py`：新增黑名单服务
- [ ] `app/middleware/auth.py`：新增认证中间件
- [ ] `app/api/v1/auth.py`：重写 auth 路由
- [ ] `app/api/deps.py`：更新依赖注入
- [ ] `app/schemas/auth.py`：更新 Schema
- [ ] `.env`：新增环境变量
- [ ] `tests/test_auth_cookie.py`：新增测试

### 15.3 不影响的部分

- 数据库模型（User, Post, Comment 等）不需要改动
- 业务逻辑（CRUD 操作）不需要改动
- 其他中间件（日志、异常处理）不需要改动

---

## 16. 给 Cursor 的额外说明

### 16.1 中间件执行顺序（关键）

Starlette 的中间件采用**洋葱模型**：
- `add_middleware` 的注册顺序决定了执行顺序
- **后注册的中间件先执行**（请求阶段）
- 推荐注册顺序：

```python
# app/main.py
app.add_middleware(AuthMiddleware)     # 第 2 注册 → 请求阶段第 2 执行
app.add_middleware(CORSMiddleware)     # 第 1 注册 → 请求阶段第 1 执行（最外层）
```

**请求阶段执行顺序**：
```
请求 → CORSMiddleware → AuthMiddleware → 路由处理
响应 ← CORSMiddleware ← AuthMiddleware ← 路由处理
```

### 16.2 Cookie 在 HTTPS vs HTTP 环境下的区别

| 环境 | Secure 属性 | 行为 |
|------|------------|------|
| 生产 (HTTPS) | `True` | Cookie 仅通过 HTTPS 传输，安全 |
| 开发 (HTTP/localhost) | `False` | Cookie 通过 HTTP 传输，开发环境必须 |

**重要**：
- `Secure=True` 的 Cookie **不会**通过 HTTP 传输
- 本地开发（`http://localhost`）如果设置 `Secure=True`，浏览器**不会发送** Cookie
- 通过 `ENVIRONMENT` 环境变量控制，`development` 时 `Secure=False`

### 16.3 测试注意事项

#### 16.3.1 单元测试

```python
# tests/test_auth_cookie.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.anyio
async def test_login_sets_cookie():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "password123"},
        )
        assert response.status_code == 200
        
        # 验证 Cookie 被设置
        cookies = response.cookies
        assert "access_token" in cookies
        assert "refresh_token" in cookies
        
        # 验证 Cookie 属性
        set_cookie_headers = response.headers.get_list("set-cookie")
        for header in set_cookie_headers:
            assert "httponly" in header.lower()
            # 注意：测试环境 Secure 可能为 False
            # assert "secure" in header.lower()  # 仅在 production 环境断言
            assert "samesite=lax" in header.lower()
            assert "path=/" in header.lower()


@pytest.mark.anyio
async def test_protected_route_requires_cookie():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 不带 Cookie → 401
        response = await client.get("/api/posts")
        assert response.status_code == 401
        assert response.json()["error"] == "COOKIE_MISSING"


@pytest.mark.anyio
async def test_protected_route_with_cookie():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 先登录获取 Cookie
        login_resp = await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "password123"},
        )
        assert login_resp.status_code == 200
        
        # 使用 Cookie 访问受保护路由
        response = await client.get("/api/posts")
        assert response.status_code == 200


@pytest.mark.anyio
async def test_auto_refresh():
    """测试自动续期：当 token 即将过期时，响应中应包含新的 Set-Cookie"""
    # 需要 mock 时间或使用短过期时间测试
    pass


@pytest.mark.anyio
async def test_logout_clears_cookie():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 登录
        await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "password123"},
        )
        
        # 登出
        response = await client.post("/api/auth/logout")
        assert response.status_code == 200
        
        # 验证 Cookie 被清除（Max-Age=0）
        set_cookie_headers = response.headers.get_list("set-cookie")
        for header in set_cookie_headers:
            assert "max-age=0" in header.lower()


@pytest.mark.anyio
async def test_token_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 登录
        await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "password123"},
        )
        
        # 查询 token 状态
        response = await client.get("/api/auth/token-status")
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is True
        assert data["user_id"] is not None
        assert data["access_token_remaining_seconds"] > 0
```

#### 16.3.2 手动测试要点

1. **localhost 无 HTTPS**：
   - `Secure` 必须为 `False`，否则浏览器不发送 Cookie
   - 确认 `ENVIRONMENT=development` 时 `Secure=False`

2. **跨域 Cookie**：
   - 前后端不同端口（前端 5173，后端 8000）时，需要 CORS `allow_credentials=True`
   - 前端 `fetch` / `axios` 需要设置 `withCredentials: true`
   - 浏览器 DevTools → Network → 检查请求是否携带 Cookie

3. **Postman / curl 测试**：
   ```bash
   # 登录
   curl -v -X POST http://localhost:8000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com","password":"password123"}'
   # 注意响应头中的 Set-Cookie
   
   # 使用 Cookie 访问
   curl -v http://localhost:8000/api/posts \
     -H "Cookie: access_token=<从登录响应中获取的token>"
   ```

4. **Cookie 调试**：
   - Chrome DevTools → Application → Cookies → localhost:8000
   - 应该能看到 `access_token` 和 `refresh_token`
   - HttpOnly 列应为 ✓（不可通过 JS 读取）

### 16.4 Redis 依赖处理

- 如果 Redis 未启动或连接失败：
  - 黑名单写入失败 → 记 warning 日志，不阻断
  - 黑名单读取失败 → 记 error 日志，视为不在黑名单（放行）
  - 开发环境可以设置 `REDIS_URL=""` 跳过 Redis，此时黑名单功能禁用

### 16.5 Starlette BaseHTTPMiddleware 注意事项

- `BaseHTTPMiddleware` 的 `dispatch` 方法中，`call_next` 返回的 `Response` 是 `StreamingResponse`
- 对 `call_next` 返回的 response 修改 headers 是安全的（在发送之前）
- `response.set_cookie()` 在 `call_next` 之后调用是有效的
- **不要用 `response.headers` 手动设置 Cookie**，使用 `response.set_cookie()` 方法

### 16.6 `set_cookie` 的 Secure 参数在测试中的处理

```python
# 在测试中，使用 httpx 的 test client 时：
# - Secure cookie 不会被 httpx 发送（模拟浏览器行为）
# - 测试环境中 ENVIRONMENT=testing 或 development，Secure=False

# 如果需要强制测试 Secure cookie：
# 可以在 config 中增加 override 机制
@pytest.fixture
def override_settings():
    settings.ENVIRONMENT = "development"
    yield
    settings.ENVIRONMENT = "testing"
```

### 16.7 前端配合事项（供后端开发者知晓）

前端需要做的改动（**不在本文档范围，但需告知前端**）：

1. 移除 localStorage 中 token 的存取逻辑
2. 移除 Authorization header 的设置逻辑
3. `axios` / `fetch` 配置 `withCredentials: true`
4. 收到 401 响应时跳转登录页
5. 无需任何续期逻辑（后端自动处理）

### 16.8 性能考量

- 黑名单检查（Redis GET）：~0.5ms，可接受
- 自动续期（JWT 签名 + Redis SET）：~2ms，仅触发时
- 续期触发频率：每个用户每 20 分钟最多触发一次（30 分钟有效期，20 分钟时开始检查）
- **不会显著影响接口性能**

### 16.9 安全最佳实践提醒

- `SECRET_KEY` 生产环境必须使用强随机字符串（至少 32 字节）
- JWT 签名算法使用 HS256 时，`SECRET_KEY` 的安全等同于密码
- 考虑定期轮换 `SECRET_KEY`（需要同时使所有现有 token 失效）
- Cookie 的 `Domain` 属性不要设置为过于宽泛的值
- 生产环境必须启用 `Secure=True`（HTTPS）

---

## 17. 文件目录结构（改动后）

```
app/
├── core/
│   ├── config.py          # [修改] 新增环境变量
│   ├── security.py        # [修改] JWT payload 结构变更，新增 jti
│   ├── cookies.py         # [新增] Cookie 工具函数
│   ├── errors.py          # [修改] 新增 AuthError 和错误码
│   └── redis.py           # [无改动] 复用现有 Redis 连接
├── middleware/
│   └── auth.py            # [新增] 认证中间件
├── services/
│   └── token_blacklist.py # [新增] Redis 黑名单服务
├── api/
│   ├── v1/
│   │   └── auth.py        # [修改] 路由重写
│   └── deps.py            # [修改] 依赖注入更新
├── schemas/
│   └── auth.py            # [修改] Schema 变更
├── main.py                # [修改] CORS 配置、中间件注册
└── .env                   # [修改] 新增环境变量

tests/
└── test_auth_cookie.py    # [新增] 认证相关测试
```

---

## 18. 实现优先级与顺序建议

| 优先级 | 任务 | 依赖 |
|--------|------|------|
| P0-1 | `app/core/config.py` 新增环境变量 | 无 |
| P0-2 | `app/core/security.py` JWT payload 变更 | P0-1 |
| P0-3 | `app/core/cookies.py` Cookie 工具函数 | P0-1 |
| P0-4 | `app/core/errors.py` 错误码 | 无 |
| P0-5 | `app/services/token_blacklist.py` 黑名单服务 | P0-1 |
| P0-6 | `app/middleware/auth.py` 认证中间件 | P0-2, P0-3, P0-4, P0-5 |
| P0-7 | `app/api/v1/auth.py` 路由重写 | P0-2, P0-3, P0-5 |
| P0-8 | `app/api/deps.py` 依赖注入更新 | P0-6 |
| P0-9 | `app/main.py` CORS + 中间件注册 | P0-6 |
| P0-10 | `app/schemas/auth.py` Schema 更新 | P0-7 |
| P0-11 | `.env` 环境变量 | P0-1 |
| P0-12 | `tests/test_auth_cookie.py` 测试 | P0-6 ~ P0-10 |

---

## 19. 回滚方案

如果上线后发现问题需要回滚：

1. **中间件回滚**：移除 `AuthMiddleware`，恢复原有的 `get_current_user` 依赖注入逻辑
2. **Cookie 回滚**：登录响应重新在 body 中返回 token
3. **黑名单回滚**：`TokenBlacklistService` 调用改为直接 pass
4. **CORS 回滚**：恢复 `allow_origins=["*"]`（但需同时关闭 `allow_credentials`）

**关键点**：向后兼容设计（Phase A）确保了即使后端升级，旧版前端仍可工作。

---

## 20. 附录

### 20.1 JWT Token 示例

**Access Token Payload（解码后）**：
```json
{
  "sub": "550e8400-e29b-41d4-a716-446655440000",
  "jti": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "iat": 1700000000,
  "exp": 1700001800,
  "token_type": "access"
}
```

**Refresh Token Payload（解码后）**：
```json
{
  "sub": "550e8400-e29b-41d4-a716-446655440000",
  "jti": "f0e1d2c3-b4a5-6789-0fed-cba987654321",
  "iat": 1700000000,
  "exp": 1700604800,
  "token_type": "refresh"
}
```

### 20.2 Redis 黑名单示例

```bash
# 续期时旧 token 被加入黑名单
> GET token_blacklist:a1b2c3d4-e5f6-7890-abcd-ef1234567890
"1"

> TTL token_blacklist:a1b2c3d4-e5f6-7890-abcd-ef1234567890
(integer) 480    # 剩余 480 秒后自动过期

# 登出时
> SET token_blacklist:f0e1d2c3-b4a5-6789-0fed-cba987654321 "1" EX 604800
OK
```

### 20.3 HTTP 请求/响应示例

**登录请求**：
```http
POST /api/auth/login HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{"email": "user@example.com", "password": "password123"}
```

**登录响应**：
```http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...; HttpOnly; SameSite=Lax; Path=/; Max-Age=1800
Set-Cookie: refresh_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800

{"user": {"id": "uuid-123", "email": "user@example.com", "nickname": "汤圆"}}
```

**带 Cookie 的 API 请求**：
```http
GET /api/posts HTTP/1.1
Host: localhost:8000
Cookie: access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...; refresh_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**自动续期响应**：
```http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: access_token=<new_token>; HttpOnly; SameSite=Lax; Path=/; Max-Age=1800
Set-Cookie: refresh_token=<new_token>; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800

{"posts": [...]}
```

### 20.4 时间线参数速查

| 参数 | 值 | 说明 |
|------|-----|------|
| access_token 有效期 | 30 分钟 | 短效，安全 |
| refresh_token 有效期 | 7 天 | 长效，用于恢复 |
| 自动续期阈值 | 10 分钟 | access_token 剩余 < 10min 时触发续期 |
| 续期窗口 | 第 20-30 分钟 | 在第 20 分钟到第 30 分钟之间，任何请求都可能触发续期 |
| 黑名单 TTL | 剩余有效期 | 过期后自动清理 |

### 20.5 安全威胁模型

| 威胁 | 防御措施 |
|------|---------|
| XSS 窃取 token | HttpOnly Cookie，JS 无法读取 |
| CSRF 攻击 | SameSite=Lax Cookie 属性 |
| Token 重放攻击 | jti 黑名单，每次续期生成新 jti |
| 中间人攻击 | Secure 属性（生产环境强制 HTTPS） |
| Token 泄露后持续使用 | 登出时加入黑名单，主动失效 |
| Redis 故障导致黑名单失效 | 降级放行（等 token 自然过期） |

---

> **文档结束**  
> 本文档应配合 Phase 0-7 的产品文档一起交给 Cursor 实现。  
> 实现完成后进入 Phase B（移除 Authorization header 兼容），届时需同步更新前端代码。

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
