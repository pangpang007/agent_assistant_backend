from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.middleware.rate_limiter import MaxBodySizeMiddleware, RateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware


def setup_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"],
        max_age=600,
    )


def setup_security_middleware(app: FastAPI) -> None:
    """
    Register Phase 7 security middleware.

    Starlette runs last-added middleware first:
    request → MaxBodySize → SecurityHeaders → RateLimit → (outer layers)
    """
    if settings.rate_limit_enabled:
        app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(MaxBodySizeMiddleware)
