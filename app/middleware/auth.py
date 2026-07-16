"""JWT Cookie 认证中间件：校验、黑名单、无感续期。"""

import logging
import time
from typing import Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from jose import ExpiredSignatureError, JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.cookies import set_auth_cookies
from app.core.security import (
    create_token_pair_from_claims,
    decode_token,
    get_token_type,
)
from app.services.token_blacklist import TokenBlacklistService

logger = logging.getLogger(__name__)

PUBLIC_PATHS = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/auth/token-status",
    "/api/health",
    "/api/crypto/public-key",
    "/docs",
    "/docs/oauth2-redirect",
    "/openapi.json",
    "/redoc",
    "/health",
}

PUBLIC_PATH_PREFIXES = (
    "/docs",
    "/redoc",
    "/static",
    "/api/published/",
    "/api/ws/",
)

# 这些路径需要认证，但响应阶段不应自动续期（例如登出已清除 Cookie）
SKIP_AUTO_REFRESH_PATHS = {
    "/api/auth/logout",
}


def _auth_error_response(code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": [],
            }
        },
    )


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Cookie / Header JWT 认证中间件。

    1. 白名单路径直接放行
    2. Cookie 优先，Authorization Bearer 过渡期兼容
    3. 校验签名 / 类型 / 黑名单
    4. access 过期时用 refresh 恢复并继续请求
    5. 剩余有效期低于阈值时自动续期
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        if self._is_public_path(request.url.path):
            return await call_next(request)

        token, source = self._extract_token(request)
        if token is None:
            return _auth_error_response("COOKIE_MISSING", "缺少认证 cookie")

        if source == "header":
            logger.warning(
                "DEPRECATION: Authorization header used for %s. "
                "Please migrate to Cookie-based auth. User-Agent: %s",
                request.url.path,
                request.headers.get("user-agent", "unknown"),
            )

        try:
            payload = decode_token(token)
        except ExpiredSignatureError:
            refreshed = await self._refresh_expired_access(request)
            if refreshed is None:
                return _auth_error_response(
                    "TOKEN_EXPIRED", "Token 已过期，请重新登录"
                )
            response = await call_next(request)
            set_auth_cookies(
                response,
                refreshed["access_token"],
                refreshed["refresh_token"],
            )
            return response
        except JWTError as exc:
            return _auth_error_response("TOKEN_INVALID", f"Token 无效: {exc}")

        if get_token_type(payload) != "access":
            return _auth_error_response("TOKEN_INVALID", "Token 类型错误")

        jti = payload.get("jti")
        if jti and await TokenBlacklistService.is_blacklisted(jti):
            return _auth_error_response("TOKEN_BLACKLISTED", "Token 已被吊销")

        request.state.user_id = payload["sub"]
        request.state.token_payload = payload
        request.state.auth_source = source

        response = await call_next(request)
        await self._maybe_auto_refresh(request, response, payload)
        return response

    def _is_public_path(self, path: str) -> bool:
        if path in PUBLIC_PATHS:
            return True
        return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)

    def _extract_token(self, request: Request) -> tuple[Optional[str], Optional[str]]:
        cookie_token = request.cookies.get("access_token")
        if cookie_token:
            return cookie_token, "cookie"

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:], "header"

        return None, None

    async def _refresh_expired_access(self, request: Request) -> Optional[dict]:
        """access 过期后尝试用 refresh_token 恢复会话。"""
        refresh_token = request.cookies.get("refresh_token")
        if not refresh_token:
            return None

        try:
            refresh_payload = decode_token(refresh_token)
        except (ExpiredSignatureError, JWTError):
            return None

        if get_token_type(refresh_payload) != "refresh":
            return None

        refresh_jti = refresh_payload.get("jti")
        if refresh_jti and await TokenBlacklistService.is_blacklisted(refresh_jti):
            return None

        (
            new_access_token,
            new_access_payload,
            new_refresh_token,
            _new_refresh_payload,
        ) = create_token_pair_from_claims(refresh_payload)

        if refresh_jti:
            await TokenBlacklistService.blacklist(
                refresh_jti, int(refresh_payload["exp"])
            )

        request.state.user_id = refresh_payload["sub"]
        request.state.token_payload = new_access_payload
        request.state.auth_source = "cookie"

        logger.info(
            "Recovered expired access token for user %s via refresh",
            refresh_payload["sub"],
        )

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
        }

    async def _maybe_auto_refresh(
        self,
        request: Request,
        response: Response,
        payload: dict,
    ) -> None:
        # 仅 Cookie 认证触发无感续期，避免吊销仍在使用的 Authorization header token
        if getattr(request.state, "auth_source", None) != "cookie":
            return

        if request.url.path in SKIP_AUTO_REFRESH_PATHS:
            return

        exp = int(payload.get("exp", 0))
        now = int(time.time())
        remaining = exp - now
        threshold = settings.jwt_auto_refresh_threshold_minutes * 60

        if remaining >= threshold:
            return

        user_id = payload["sub"]
        old_jti = payload.get("jti")

        (
            new_access_token,
            _new_access_payload,
            new_refresh_token,
            _new_refresh_payload,
        ) = create_token_pair_from_claims(payload)

        if old_jti:
            await TokenBlacklistService.blacklist(old_jti, exp)

        old_refresh_token = request.cookies.get("refresh_token")
        if old_refresh_token:
            try:
                old_refresh_payload = decode_token(old_refresh_token)
                old_refresh_jti = old_refresh_payload.get("jti")
                if old_refresh_jti:
                    await TokenBlacklistService.blacklist(
                        old_refresh_jti, int(old_refresh_payload["exp"])
                    )
            except JWTError:
                pass

        set_auth_cookies(response, new_access_token, new_refresh_token)
        logger.info(
            "Auto-refreshed token for user %s, old_jti=%s, remaining=%ss",
            user_id,
            old_jti,
            remaining,
        )
