"""团队服务：处理团队创建、加入、成员管理、删除"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.security import generate_invite_code
from app.models.team import Team
from app.models.user import User


class TeamService:
    @staticmethod
    async def create_team(db: AsyncSession, user: User, name: str) -> dict:
        if user.account_type == "team":
            raise AppException(
                code="ALREADY_HAS_TEAM",
                message="您已拥有一个团队",
                status_code=409,
            )

        if user.team_id is not None:
            raise AppException(
                code="ALREADY_IN_TEAM",
                message="您已加入其他团队，请先退出后再创建",
                status_code=409,
            )

        invite_code = await TeamService._generate_unique_invite_code(db)

        team = Team(
            name=name,
            owner_id=user.id,
            invite_code=invite_code,
        )
        db.add(team)
        await db.flush()

        user.team_id = team.id
        user.account_type = "team"

        await db.commit()
        await db.refresh(team)
        await db.refresh(user)

        return {"team": team, "user": user}

    @staticmethod
    async def join_team(db: AsyncSession, user: User, invite_code: str) -> dict:
        if user.account_type == "team":
            raise AppException(
                code="ALREADY_HAS_TEAM",
                message="您已拥有一个团队，无法加入其他团队",
                status_code=409,
            )
        if user.team_id is not None:
            raise AppException(
                code="ALREADY_IN_TEAM",
                message="您已在一个团队中，请先退出当前团队",
                status_code=409,
            )

        invite_code_upper = invite_code.upper()
        result = await db.execute(
            select(Team).where(Team.invite_code == invite_code_upper)
        )
        team = result.scalar_one_or_none()
        if team is None:
            raise AppException(
                code="INVALID_INVITE_CODE",
                message="邀请码无效",
                status_code=404,
            )

        member_count_result = await db.execute(
            select(func.count()).select_from(User).where(User.team_id == team.id)
        )
        member_count = member_count_result.scalar() or 0
        if member_count >= settings.team_max_members:
            raise AppException(
                code="TEAM_FULL",
                message=f"团队人数已达上限（{settings.team_max_members}人）",
                status_code=400,
            )

        user.team_id = team.id
        await db.commit()
        await db.refresh(user)

        return {"team": team, "user": user}

    @staticmethod
    async def get_members(db: AsyncSession, team: Team) -> list[dict]:
        result = await db.execute(select(User).where(User.team_id == team.id))
        members = result.scalars().all()

        member_list = []
        for member in members:
            role = "owner" if member.id == team.owner_id else "member"
            member_list.append(
                {
                    "id": member.id,
                    "email": member.email,
                    "username": member.username,
                    "avatar_url": member.avatar_url,
                    "account_type": member.account_type,
                    "role": role,
                    "joined_at": member.updated_at,
                }
            )

        return member_list

    @staticmethod
    async def remove_member(
        db: AsyncSession,
        team: Team,
        owner_user: User,
        target_user_id: str,
    ) -> None:
        if str(owner_user.id) == target_user_id:
            raise AppException(
                code="CANNOT_REMOVE_SELF",
                message="不能移除自己，如需离开请使用删除团队功能",
                status_code=400,
            )

        result = await db.execute(select(User).where(User.id == uuid.UUID(target_user_id)))
        target_user = result.scalar_one_or_none()
        if target_user is None:
            raise AppException(
                code="USER_NOT_FOUND",
                message="用户不存在",
                status_code=404,
            )

        if target_user.team_id != team.id:
            raise AppException(
                code="USER_NOT_IN_TEAM",
                message="该用户不属于当前团队",
                status_code=400,
            )

        target_user.team_id = None
        await db.commit()

    @staticmethod
    async def reset_invite_code(db: AsyncSession, team: Team) -> str:
        new_code = await TeamService._generate_unique_invite_code(db)
        team.invite_code = new_code
        await db.commit()
        return new_code

    @staticmethod
    async def delete_team(db: AsyncSession, team: Team, owner_user: User) -> int:
        result = await db.execute(
            select(User).where(User.team_id == team.id, User.id != owner_user.id)
        )
        members = result.scalars().all()
        affected_count = len(members)

        for member in members:
            member.team_id = None

        owner_user.team_id = None
        owner_user.account_type = "personal"

        await db.delete(team)
        await db.flush()
        return affected_count

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
