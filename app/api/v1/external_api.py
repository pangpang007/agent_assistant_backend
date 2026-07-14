from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_key_auth import get_workflow_by_api_key
from app.core.database import get_db
from app.models.workflow import Workflow
from app.schemas.external_api import ExternalApiRunRequest
from app.services.external_execution import ExternalExecutionService
from app.services.rate_limit_service import RateLimitService

router = APIRouter(tags=["External API"])


@router.post("/published/{api_key}/run")
async def run_published_workflow(
    api_key: str,
    body: ExternalApiRunRequest,
    request: Request,
    workflow: Workflow = Depends(get_workflow_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """外部系统调用已发布的工作流（路径 API Key 为主认证）。"""
    rate_limit = RateLimitService()
    is_allowed, limit_info = await rate_limit.check_rate_limit(api_key)

    if not is_allowed:
        retry_after = limit_info.get("retry_after") or 60
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMITED",
                "message": "调用频率超限",
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    service = ExternalExecutionService()
    result = await service.run_workflow(db, workflow, body.input)
    return {"code": 0, "message": "success", "data": result}
