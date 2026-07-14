from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.services.log_service import LogService

router = APIRouter()


@router.get("")
async def list_logs(
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    level: Optional[str] = Query(None, pattern="^(info|warn|error)$"),
    execution_id: Optional[UUID] = Query(None),
    node_id: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    search: Optional[str] = Query(None, max_length=200),
):
    service = LogService(db)
    result = await service.list_global_logs(
        user_id=user.id,
        page=page,
        page_size=page_size,
        level=level,
        execution_id=execution_id,
        node_id=node_id,
        start_time=start_time,
        end_time=end_time,
        search=search,
    )
    return {"code": 0, "message": "success", "data": result.model_dump()}


@router.get("/{log_id}")
async def get_log(
    log_id: UUID,
    db: DBSession,
    user: CurrentUser,
):
    service = LogService(db)
    result = await service.get_log_detail(log_id, user.id)
    return {"code": 0, "message": "success", "data": result.model_dump()}
