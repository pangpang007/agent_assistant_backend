from typing import Optional

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.publish_api import TogglePublishedApiRequest
from app.services.publish_api_service import PublishApiService

router = APIRouter(prefix="/published-apis", tags=["Published APIs"])


@router.get("")
async def list_published_apis(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = PublishApiService()
    data = await service.list_published_apis(db, str(current_user.id))
    return {"code": 0, "message": "success", "data": data}


@router.put("/{workflow_id}/toggle")
async def toggle_api(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    body: Optional[TogglePublishedApiRequest] = Body(default=None),
):
    service = PublishApiService()
    is_active = body.is_active if body else None
    data = await service.toggle_api(
        db, str(current_user.id), workflow_id, is_active
    )
    return {"code": 0, "message": "success", "data": data}
