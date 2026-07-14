from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.search_service import SearchService

router = APIRouter(tags=["Search"])


@router.get("/search")
async def global_search(
    q: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    type: str | None = Query(
        default=None,
        pattern="^(workflow|agent|knowledge|template)$",
        description="限定搜索类型",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SearchService()
    data = await service.search(db, str(current_user.id), q, type)
    return {"code": 0, "message": "success", "data": data}
