from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.schemas.env_variable import EnvVarCreateRequest, EnvVarUpdateRequest
from app.services.env_service import EnvService, format_env_var

router = APIRouter()


@router.get("")
async def list_env_vars(
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    type: Optional[str] = Query(None, pattern="^(string|secret)$"),
):
    service = EnvService(db)
    result = await service.list_env_vars(
        user.id, page=page, page_size=page_size, var_type=type
    )
    return {"code": 0, "message": "success", "data": result.model_dump()}


@router.post("")
async def create_env_var(
    body: EnvVarCreateRequest,
    db: DBSession,
    user: CurrentUser,
):
    service = EnvService(db)
    env_var = await service.create_env_var(user.id, body.key, body.value, body.type)
    return {
        "code": 0,
        "message": "success",
        "data": format_env_var(env_var).model_dump(),
    }


@router.put("/{env_var_id}")
async def update_env_var(
    env_var_id: UUID,
    body: EnvVarUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    service = EnvService(db)
    env_var = await service.update_env_var(
        env_var_id, user.id, body.value, body.type
    )
    return {
        "code": 0,
        "message": "success",
        "data": format_env_var(env_var).model_dump(),
    }


@router.delete("/{env_var_id}")
async def delete_env_var(
    env_var_id: UUID,
    db: DBSession,
    user: CurrentUser,
):
    service = EnvService(db)
    await service.delete_env_var(env_var_id, user.id)
    return {
        "code": 0,
        "message": "success",
        "data": {"message": "环境变量已删除", "env_var_id": str(env_var_id)},
    }
