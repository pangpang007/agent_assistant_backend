"""用户服务：处理个人资料查看/更新、密码修改"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.security import hash_password, verify_password
from app.models.team import Team
from app.models.user import User


class UserService:
    @staticmethod
    async def get_profile(db: AsyncSession, user: User) -> dict:
        team = None
        if user.team_id:
            result = await db.execute(select(Team).where(Team.id == user.team_id))
            team = result.scalar_one_or_none()

        return {"user": user, "team": team}

    @staticmethod
    async def update_user(
        db: AsyncSession,
        user: User,
        username: str | None = None,
    ) -> User:
        if username is None:
            raise AppException(
                code="NO_FIELDS_TO_UPDATE",
                message="未提供任何需要更新的字段",
                status_code=400,
            )

        result = await db.execute(
            select(User).where(User.username == username, User.id != user.id)
        )
        if result.scalar_one_or_none() is not None:
            raise AppException(
                code="USERNAME_ALREADY_TAKEN",
                message="该用户名已被占用",
                status_code=409,
            )

        user.username = username
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def change_password(
        db: AsyncSession,
        user: User,
        old_password: str,
        new_password: str,
    ) -> None:
        if not verify_password(old_password, user.password_hash):
            raise AppException(
                code="INVALID_OLD_PASSWORD",
                message="旧密码不正确",
                status_code=400,
            )

        if old_password == new_password:
            raise AppException(
                code="SAME_PASSWORD",
                message="新密码不能与旧密码相同",
                status_code=400,
            )

        user.password_hash = hash_password(new_password)
        await db.commit()
