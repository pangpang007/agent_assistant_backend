import uuid
from typing import Annotated, Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AuthError, ForbiddenException, UnauthorizedException
from app.core.security import (
    decode_token,
    get_token_type,
    is_token_blacklisted,
    try_decode_token,
)
from app.models.team import Team
from app.models.user import User

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user_id(request: Request) -> str:
    """
    从 request.state 获取当前用户 ID（由 AuthMiddleware 注入）。
    过渡期：若中间件未注入，回退解析 Cookie / Authorization header。
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return str(user_id)

    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise AuthError(code="COOKIE_MISSING", message="未认证")

    payload = try_decode_token(token)
    if payload is None:
        raise AuthError(code="TOKEN_INVALID", message="无效或过期的 Token")

    if get_token_type(payload) != "access":
        raise AuthError(code="TOKEN_INVALID", message="Token 类型不正确")

    if await is_token_blacklisted(token):
        raise AuthError(code="TOKEN_BLACKLISTED", message="Token 已被吊销")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthError(code="TOKEN_INVALID", message="无效 Token")

    return str(user_id)


async def get_current_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(security_scheme)
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    user_id_str = getattr(request.state, "user_id", None)

    if not user_id_str:
        token = request.cookies.get("access_token")
        if not token and credentials is not None:
            token = credentials.credentials

        if not token:
            raise UnauthorizedException("未授权，请先登录")

        payload = try_decode_token(token)
        if payload is None:
            raise UnauthorizedException("无效或过期的 Token")

        if get_token_type(payload) != "access":
            raise UnauthorizedException("Token 类型不正确")

        if await is_token_blacklisted(token):
            raise UnauthorizedException("Token 已被撤销")

        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise UnauthorizedException("无效 Token")

    try:
        user_id = uuid.UUID(str(user_id_str))
    except ValueError:
        raise UnauthorizedException("无效 Token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise UnauthorizedException("用户不存在")

    if not user.is_active:
        raise UnauthorizedException("账号已被禁用")

    return user


async def require_owner(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Team:
    if current_user.team_id is None:
        raise ForbiddenException("您不属于任何团队")

    if current_user.account_type != "team":
        raise ForbiddenException("仅团队 Owner 可执行此操作")

    result = await db.execute(select(Team).where(Team.id == current_user.team_id))
    team = result.scalar_one_or_none()

    if team is None:
        raise ForbiddenException("团队不存在")

    if team.owner_id != current_user.id:
        raise ForbiddenException("仅团队 Owner 可执行此操作")

    return team


async def get_current_team(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Optional[Team]:
    if current_user.team_id is None:
        return None

    result = await db.execute(select(Team).where(Team.id == current_user.team_id))
    return result.scalar_one_or_none()


CurrentUser = Annotated[User, Depends(get_current_user)]
DBSession = Annotated[AsyncSession, Depends(get_db)]
OwnerTeam = Annotated[Team, Depends(require_owner)]
