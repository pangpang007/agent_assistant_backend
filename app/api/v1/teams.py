from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_owner
from app.core.database import get_db
from app.models.team import Team
from app.models.user import User
from app.schemas.team import JoinTeamRequest, TeamCreateRequest, TeamResponse
from app.schemas.user import UserResponse
from app.services.team_service import TeamService

router = APIRouter()


@router.post("")
async def create_team(
    body: TeamCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await TeamService.create_team(
        db=db,
        user=current_user,
        name=body.name,
    )

    return {
        "code": 0,
        "message": "success",
        "data": {
            "team": TeamResponse.model_validate(result["team"]).model_dump(),
            "user": UserResponse.model_validate(result["user"]).model_dump(),
        },
    }


@router.post("/join")
async def join_team(
    body: JoinTeamRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await TeamService.join_team(
        db=db,
        user=current_user,
        invite_code=body.invite_code,
    )

    member_count_result = await db.execute(
        select(func.count()).select_from(User).where(User.team_id == result["team"].id)
    )
    member_count = member_count_result.scalar() or 0

    team_data = TeamResponse.model_validate(result["team"]).model_dump()
    team_data["member_count"] = member_count

    return {
        "code": 0,
        "message": "success",
        "data": {
            "team": team_data,
            "user": UserResponse.model_validate(result["user"]).model_dump(),
        },
    }


@router.get("/members")
async def get_members(
    team: Team = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    members = await TeamService.get_members(db=db, team=team)

    return {
        "code": 0,
        "message": "success",
        "data": {
            "team_id": str(team.id),
            "team_name": team.name,
            "members": members,
            "total": len(members),
        },
    }


@router.delete("/members/{user_id}")
async def remove_member(
    user_id: str,
    current_user: User = Depends(get_current_user),
    team: Team = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    await TeamService.remove_member(
        db=db,
        team=team,
        owner_user=current_user,
        target_user_id=user_id,
    )

    return {
        "code": 0,
        "message": "success",
        "data": {"message": "成员已移除"},
    }


@router.post("/invite-code/reset")
async def reset_invite_code(
    team: Team = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    new_code = await TeamService.reset_invite_code(db=db, team=team)

    return {
        "code": 0,
        "message": "success",
        "data": {
            "invite_code": new_code,
            "message": "邀请码已重置",
        },
    }


@router.delete("")
async def delete_team(
    current_user: User = Depends(get_current_user),
    team: Team = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    affected = await TeamService.delete_team(
        db=db,
        team=team,
        owner_user=current_user,
    )

    return {
        "code": 0,
        "message": "success",
        "data": {
            "message": "团队已删除",
            "affected_members": affected,
        },
    }
