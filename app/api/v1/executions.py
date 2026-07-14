import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.redis import get_redis
from app.models.user import User
from app.schemas.execution import (
    LogListParams,
    ReviewActionRequest,
)
from app.services.execution_service import ExecutionService
from app.services.log_service import LogService

router = APIRouter()


@router.get("")
async def list_executions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    workflow_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    redis = get_redis()
    service = ExecutionService(db, redis)
    result = await service.list_executions(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        workflow_id=workflow_id,
        status=status,
    )
    return {
        "code": 0,
        "message": "success",
        "data": result.model_dump(),
    }


@router.get("/{execution_id}")
async def get_execution(
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    redis = get_redis()
    service = ExecutionService(db, redis)
    result = await service.get_execution_detail(execution_id, current_user.id)
    return {
        "code": 0,
        "message": "success",
        "data": result.model_dump(),
    }


@router.get("/{execution_id}/nodes")
async def get_execution_nodes(
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    redis = get_redis()
    service = ExecutionService(db, redis)
    nodes = await service.get_execution_nodes(execution_id, current_user.id)
    return {
        "code": 0,
        "message": "success",
        "data": [n.model_dump() for n in nodes],
    }


@router.get("/{execution_id}/logs")
async def get_execution_logs(
    execution_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    node_id: Optional[str] = Query(None),
    level: Optional[str] = Query(None, pattern="^(info|warn|error)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LogService(db)
    params = LogListParams(
        page=page,
        page_size=page_size,
        execution_id=execution_id,
        node_id=node_id,
        level=level,
    )
    result = await service.list_logs(
        user_id=current_user.id,
        params=params,
        execution_id=execution_id,
    )
    return {
        "code": 0,
        "message": "success",
        "data": result.model_dump(),
    }


@router.post("/{execution_id}/cancel")
async def cancel_execution(
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    redis = get_redis()
    service = ExecutionService(db, redis)
    result = await service.cancel_execution(execution_id, current_user.id)
    return {
        "code": 0,
        "message": "success",
        "data": result.model_dump(),
    }


@router.post("/{execution_id}/nodes/{node_id}/review")
async def submit_review(
    execution_id: uuid.UUID,
    node_id: str,
    body: ReviewActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    redis = get_redis()
    service = ExecutionService(db, redis)
    result = await service.submit_review(
        execution_id=execution_id,
        node_id=node_id,
        user_id=current_user.id,
        action=body.action,
        comment=body.comment,
        modified_data=body.modified_data,
    )
    return {
        "code": 0,
        "message": "success",
        "data": result.model_dump(),
    }
