"""认证服务：处理注册、登录、token 刷新、登出"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.security import (
    blacklist_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_invite_code,
    hash_password,
    is_token_blacklisted,
    verify_password,
)
from app.models.team import Team
from app.models.user import User


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
        result = await db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none() is not None:
            raise AppException(
                code="EMAIL_ALREADY_REGISTERED",
                message="该邮箱已被注册",
                status_code=409,
            )

        result = await db.execute(select(User).where(User.username == username))
        if result.scalar_one_or_none() is not None:
            raise AppException(
                code="USERNAME_ALREADY_TAKEN",
                message="该用户名已被占用",
                status_code=409,
            )

        user = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
            account_type=account_type,
            is_active=True,
        )
        db.add(user)
        await db.flush()

        team = None
        if account_type == "team" and team_name:
            invite_code = await AuthService._generate_unique_invite_code(db)
            team = Team(
                name=team_name,
                owner_id=user.id,
                invite_code=invite_code,
            )
            db.add(team)
            await db.flush()

            user.team_id = team.id
            user.account_type = "team"

        await db.commit()
        await db.refresh(user)
        if team:
            await db.refresh(team)

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
    async def login(db: AsyncSession, email: str, password: str) -> dict:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None:
            raise AppException(
                code="INVALID_CREDENTIALS",
                message="邮箱或密码错误",
                status_code=401,
            )

        if not user.is_active:
            raise AppException(
                code="ACCOUNT_DISABLED",
                message="账号已被禁用",
                status_code=403,
            )

        if not verify_password(password, user.password_hash):
            raise AppException(
                code="INVALID_CREDENTIALS",
                message="邮箱或密码错误",
                status_code=401,
            )

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
    async def refresh_token(db: AsyncSession, token: str) -> dict:
        payload = decode_token(token)
        if payload is None:
            raise AppException(
                code="INVALID_TOKEN",
                message="Token 无效或已过期",
                status_code=401,
            )

        if payload.get("type") != "refresh":
            raise AppException(
                code="INVALID_TOKEN_TYPE",
                message="需要 refresh_token",
                status_code=401,
            )

        if await is_token_blacklisted(token):
            raise AppException(
                code="TOKEN_REVOKED",
                message="Token 已被撤销",
                status_code=401,
            )

        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise AppException(code="INVALID_TOKEN", message="无效 Token", status_code=401)

        result = await db.execute(select(User).where(User.id == uuid.UUID(user_id_str)))
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            raise AppException(
                code="USER_INACTIVE",
                message="用户不存在或已被禁用",
                status_code=401,
            )

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
        exp_timestamp = payload.get("exp")
        if exp_timestamp:
            expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
            await blacklist_token(token, expires_at)

    @staticmethod
    async def _generate_unique_invite_code(db: AsyncSession) -> str:
        for _ in range(3):
            code = generate_invite_code()
            result = await db.execute(select(Team).where(Team.invite_code == code))
            if result.scalar_one_or_none() is None:
                return code
        raise AppException(
            code="INVITE_CODE_GENERATION_FAILED",
            message="邀请码生成失败，请重试",
            status_code=500,
        )
