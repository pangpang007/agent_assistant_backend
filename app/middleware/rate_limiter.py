"""Global rate limiting + max body size middleware."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

# Paths excluded from harsh global rate limits
_SKIP_PATHS = frozenset(
    {
        "/health",
        "/api/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)
_SKIP_PREFIXES = (
    "/api/crypto",
    "/docs",
    "/redoc",
)


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies based on Content-Length."""

    async def dispatch(self, request: Request, call_next):
        max_size = settings.max_request_body_size
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_size:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": {
                                "code": "PAYLOAD_TOO_LARGE",
                                "message": "请求体过大，最大允许 10MB",
                            }
                        },
                    )
            except ValueError:
                pass
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Light global rate limiting by IP / category.

    External published runs use RateLimitService (API key) separately.
    """

    async def dispatch(self, request: Request, call_next):
        if not settings.rate_limit_enabled:
            return await call_next(request)

        path = request.url.path
        if path in _SKIP_PATHS or any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        # External published runs: skip global limiter (per-key in service)
        if "/published/" in path and path.endswith("/run"):
            return await call_next(request)

        if "/auth/" in path:
            category = "auth"
            limit = settings.rate_limit_per_minute_auth
        elif "/publish-api" in path:
            category = "publish"
            limit = settings.rate_limit_per_minute_publish
        else:
            category = "default"
            limit = settings.rate_limit_per_minute_default

        client_id = self._get_client_id(request)
        rate_key = f"rate:{category}:{client_id}"

        try:
            from app.core.redis import get_redis

            redis = get_redis()
            count = await redis.incr(rate_key)
            if count == 1:
                await redis.expire(rate_key, 60)

            if count > limit:
                ttl = await redis.ttl(rate_key)
                retry_after = max(1, ttl)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "RATE_LIMITED",
                            "message": "请求频率超限，请稍后重试",
                            "retry_after": retry_after,
                        }
                    },
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
            return response
        except Exception:
            return await call_next(request)

    def _get_client_id(self, request: Request) -> str:
        if hasattr(request.state, "user_id") and request.state.user_id:
            return str(request.state.user_id)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
