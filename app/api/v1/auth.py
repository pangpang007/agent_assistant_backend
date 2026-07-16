import time

from typing import Optional

from fastapi import APIRouter, Body, Depends, Request, Response
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.core.database import get_db
from app.core.exceptions import AuthError
from app.core.security import decode_token, decode_token_unverified_exp, get_token_type
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest
from app.schemas.team import TeamResponse
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService
from app.services.token_blacklist import TokenBlacklistService

router = APIRouter()


@router.post("/register")
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    result = await AuthService.register(
        db=db,
        email=body.email,
        username=body.username,
        password=body.password,
        account_type=body.account_type,
        team_name=body.team_name,
    )

    set_auth_cookies(response, result["access_token"], result["refresh_token"])

    return {
        "code": 0,
        "message": "success",
        "data": {
            "user": UserResponse.model_validate(result["user"]).model_dump(),
            "team": TeamResponse.model_validate(result["team"]).model_dump()
            if result["team"]
            else None,
            # Phase A: body 中仍返回 token，兼容旧前端；Phase B 将移除
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"],
            "token_type": "bearer",
        },
    }


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    result = await AuthService.login(
        db=db,
        email=body.email,
        password=body.password,
    )

    set_auth_cookies(response, result["access_token"], result["refresh_token"])

    return {
        "code": 0,
        "message": "success",
        "data": {
            "user": UserResponse.model_validate(result["user"]).model_dump(),
            # Phase A: body 中仍返回 token，兼容旧前端；Phase B 将移除
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"],
            "token_type": "bearer",
        },
    }


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    body: Optional[RefreshRequest] = Body(default=None),
):
    token = body.refresh_token if body else None
    if not token:
        token = request.cookies.get("refresh_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise AuthError(code="COOKIE_MISSING", message="缺少 refresh_token cookie")

    # 同步吊销旧 access_token（若存在）
    old_access = request.cookies.get("access_token")
    if old_access:
        old_payload = decode_token_unverified_exp(old_access)
        if old_payload:
            old_jti = old_payload.get("jti")
            if old_jti and old_payload.get("exp"):
                await TokenBlacklistService.blacklist(old_jti, int(old_payload["exp"]))

    result = await AuthService.refresh_token(db=db, token=token)
    set_auth_cookies(response, result["access_token"], result["refresh_token"])

    return {
        "code": 0,
        "message": "success",
        "data": {
            "message": result["message"],
            # Phase A 兼容
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"],
            "expires_in": result["expires_in"],
            "token_type": "bearer",
        },
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
):
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")

    if not access_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            access_token = auth_header[7:]

    await AuthService.logout(access_token=access_token, refresh_token=refresh_token)
    clear_auth_cookies(response)

    return {
        "code": 0,
        "message": "success",
        "data": {"message": "已成功登出"},
    }


@router.get("/token-status")
async def token_status(request: Request):
    """供前端检查 token 状态（UI / 调试）。"""
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

    if access_token:
        try:
            payload = decode_token(access_token)
            jti = payload.get("jti")
            is_blacklisted = jti and await TokenBlacklistService.is_blacklisted(jti)
            if not is_blacklisted and get_token_type(payload) == "access":
                exp = int(payload["exp"])
                remaining = exp - now
                result.update(
                    {
                        "is_valid": True,
                        "user_id": payload["sub"],
                        "access_token_expires_at": exp,
                        "access_token_remaining_seconds": max(remaining, 0),
                        "access_token_needs_refresh": remaining
                        < (settings.jwt_auto_refresh_threshold_minutes * 60),
                    }
                )
        except JWTError:
            pass

    if refresh_token:
        try:
            payload = decode_token(refresh_token)
            jti = payload.get("jti")
            is_blacklisted = jti and await TokenBlacklistService.is_blacklisted(jti)
            if not is_blacklisted and get_token_type(payload) == "refresh":
                result["refresh_token_valid"] = True
                result["refresh_token_expires_at"] = int(payload["exp"])
        except JWTError:
            pass

    return {
        "code": 0,
        "message": "success",
        "data": result,
    }
