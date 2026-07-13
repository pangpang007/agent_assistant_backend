from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest
from app.schemas.team import TeamResponse
from app.schemas.user import UserProfileResponse, UserUpdateRequest
from app.services.user_service import UserService

router = APIRouter()


def _build_profile_response(result: dict) -> dict:
    user_data = UserProfileResponse(
        id=result["user"].id,
        email=result["user"].email,
        username=result["user"].username,
        avatar_url=result["user"].avatar_url,
        account_type=result["user"].account_type,
        team_id=result["user"].team_id,
        team=TeamResponse.model_validate(result["team"]).model_dump()
        if result["team"]
        else None,
        is_active=result["user"].is_active,
        created_at=result["user"].created_at,
        updated_at=result["user"].updated_at,
    )
    return user_data.model_dump()


@router.get("/profile")
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await UserService.get_profile(db=db, user=current_user)

    return {
        "code": 0,
        "message": "success",
        "data": _build_profile_response(result),
    }


@router.patch("/profile")
async def update_profile(
    body: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    updated_user = await UserService.update_user(
        db=db,
        user=current_user,
        username=body.username,
    )

    result = await UserService.get_profile(db=db, user=updated_user)

    return {
        "code": 0,
        "message": "success",
        "data": _build_profile_response(result),
    }


@router.post("/profile/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await UserService.change_password(
        db=db,
        user=current_user,
        old_password=body.old_password,
        new_password=body.new_password,
    )

    return {
        "code": 0,
        "message": "success",
        "data": {"message": "密码修改成功"},
    }
