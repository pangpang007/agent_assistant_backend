import uuid
from typing import Annotated, Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import decode_token, is_token_blacklisted
from app.models.team import Team
from app.models.user import User

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(security_scheme)
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        raise UnauthorizedException("未授权，请先登录")

    token = credentials.credentials

    payload = decode_token(token)
    if payload is None:
        raise UnauthorizedException("无效或过期的 Token")

    if payload.get("type") != "access":
        raise UnauthorizedException("Token 类型不正确")

    if await is_token_blacklisted(token):
        raise UnauthorizedException("Token 已被撤销")

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise UnauthorizedException("无效 Token")

    try:
        user_id = uuid.UUID(user_id_str)
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
