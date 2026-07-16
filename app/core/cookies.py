"""HTTP-only Cookie helpers for JWT auth."""

from fastapi import Response

from app.core.config import settings


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
) -> None:
    """Set access_token and refresh_token as HTTP-only cookies."""
    is_production = settings.is_production

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_production,
        samesite="lax",
        path="/",
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=is_production,
        samesite="lax",
        path="/",
        max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
    )


def clear_auth_cookies(response: Response) -> None:
    """Clear auth cookies (logout)."""
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
