import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.agent import (
    AgentCopyRequest,
    AgentCreateRequest,
    AgentUpdateRequest,
)
from app.services.agent_service import AgentService

router = APIRouter()


@router.get("")
async def list_agents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=100),
    is_preset: bool | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await AgentService.list_agents(
        db=db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        keyword=keyword,
        is_preset=is_preset,
    )
    return {"code": 0, "message": "success", "data": data}


@router.get("/{agent_id}")
async def get_agent(
    agent_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await AgentService.get_agent_detail(
        db=db, agent_id=agent_id, current_user=current_user
    )
    return {"code": 0, "message": "success", "data": data}


@router.post("")
async def create_agent(
    body: AgentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await AgentService.create_agent(
        db=db, user_id=current_user.id, data=body.model_dump()
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": str(agent.id),
            "name": agent.name,
            "message": "Agent 创建成功",
        },
    }


@router.put("/{agent_id}")
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await AgentService.update_agent(
        db=db,
        agent_id=agent_id,
        current_user=current_user,
        data=body.model_dump(exclude_unset=True),
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": str(agent.id),
            "name": agent.name,
            "message": "Agent 更新成功",
        },
    }


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await AgentService.delete_agent(
        db=db, agent_id=agent_id, current_user=current_user
    )
    return {
        "code": 0,
        "message": "success",
        "data": {"message": "Agent 已删除", "agent_id": str(agent_id)},
    }


@router.post("/{agent_id}/copy")
async def copy_agent(
    agent_id: uuid.UUID,
    body: AgentCopyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await AgentService.copy_agent(
        db=db,
        agent_id=agent_id,
        current_user=current_user,
        new_name=body.name,
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": str(agent.id),
            "name": agent.name,
            "original_id": str(agent_id),
            "message": "Agent 复制成功",
        },
    }
