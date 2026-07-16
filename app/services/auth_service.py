"""认证服务：处理注册、登录、token 刷新、登出"""

import uuid

from jose import ExpiredSignatureError, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException, AuthError
from app.core.security import (
    create_token_pair,
    create_token_pair_from_claims,
    decode_token,
    decode_token_unverified_exp,
    generate_invite_code,
    get_token_type,
    hash_password,
    verify_password,
)
from app.models.team import Team
from app.models.user import User
from app.services.token_blacklist import TokenBlacklistService


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

        access_token, access_payload, refresh_token, refresh_payload = create_token_pair(
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
            "access_payload": access_payload,
            "refresh_payload": refresh_payload,
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

        access_token, access_payload, refresh_token, refresh_payload = create_token_pair(
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
            "access_payload": access_payload,
            "refresh_payload": refresh_payload,
        }

    @staticmethod
    async def refresh_token(db: AsyncSession, token: str) -> dict:
        try:
            payload = decode_token(token)
        except ExpiredSignatureError:
            raise AuthError(
                code="TOKEN_EXPIRED",
                message="refresh_token 已过期，请重新登录",
            )
        except JWTError:
            raise AuthError(code="TOKEN_INVALID", message="refresh_token 无效")

        if get_token_type(payload) != "refresh":
            raise AppException(
                code="INVALID_TOKEN_TYPE",
                message="需要 refresh_token",
                status_code=401,
            )

        jti = payload.get("jti")
        if jti and await TokenBlacklistService.is_blacklisted(jti):
            raise AuthError(code="TOKEN_BLACKLISTED", message="Token 已被吊销")

        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise AuthError(code="TOKEN_INVALID", message="无效 Token")

        result = await db.execute(select(User).where(User.id == uuid.UUID(user_id_str)))
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            raise AppException(
                code="USER_INACTIVE",
                message="用户不存在或已被禁用",
                status_code=401,
            )

        if jti:
            await TokenBlacklistService.blacklist(jti, int(payload["exp"]))

        access_token, access_payload, refresh_token, refresh_payload = (
            create_token_pair_from_claims(
                {
                    "sub": str(user.id),
                    "email": user.email,
                    "account_type": user.account_type,
                    "team_id": str(user.team_id) if user.team_id else None,
                    "username": user.username,
                }
            )
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "access_payload": access_payload,
            "refresh_payload": refresh_payload,
            "expires_in": settings.jwt_access_token_expire_minutes * 60,
            "message": "Token 已刷新",
        }

    @staticmethod
    async def logout(
        access_token: str | None = None,
        refresh_token: str | None = None,
    ) -> None:
        for token in (access_token, refresh_token):
            if not token:
                continue
            payload = decode_token_unverified_exp(token)
            if not payload:
                continue
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                await TokenBlacklistService.blacklist(jti, int(exp))

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
