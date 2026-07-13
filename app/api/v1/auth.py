from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest
from app.schemas.team import TeamResponse
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/register")
async def register(
    body: RegisterRequest,
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

    return {
        "code": 0,
        "message": "success",
        "data": {
            "user": UserResponse.model_validate(result["user"]).model_dump(),
            "team": TeamResponse.model_validate(result["team"]).model_dump()
            if result["team"]
            else None,
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"],
            "token_type": "bearer",
        },
    }


@router.post("/login")
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
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
        },
    }


@router.post("/refresh")
async def refresh(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    token = body.refresh_token
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")

    if not token:
        from app.core.exceptions import AppException

        raise AppException(
            code="INVALID_TOKEN",
            message="Token 无效或已过期",
            status_code=401,
        )

    result = await AuthService.refresh_token(db=db, token=token)

    return {
        "code": 0,
        "message": "success",
        "data": result,
    }


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""

    payload = decode_token(token)
    if payload:
        await AuthService.logout(token=token, payload=payload)

    return {
        "code": 0,
        "message": "success",
        "data": {"message": "登出成功"},
    }
