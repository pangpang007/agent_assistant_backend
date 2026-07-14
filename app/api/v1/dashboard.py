from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService()
    data = await service.get_stats(db, str(current_user.id))
    return {"code": 0, "message": "success", "data": data}


@router.get("/token-usage")
async def get_token_usage(
    days: int = Query(default=7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService()
    data = await service.get_token_usage(db, str(current_user.id), days)
    return {"code": 0, "message": "success", "data": data}


@router.get("/recent-workflows")
async def get_recent_workflows(
    limit: int = Query(default=5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService()
    data = await service.get_recent_workflows(db, str(current_user.id), limit)
    return {"code": 0, "message": "success", "data": data}


@router.get("/recent-executions")
async def get_recent_executions(
    limit: int = Query(default=5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService()
    data = await service.get_recent_executions(db, str(current_user.id), limit)
    return {"code": 0, "message": "success", "data": data}
