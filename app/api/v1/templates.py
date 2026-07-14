from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.schemas.template import (
    TemplateDetailResponse,
    UseTemplateRequest,
)
from app.services.template_service import TemplateService

router = APIRouter()


def _workflow_detail(workflow) -> dict:
    return {
        "id": str(workflow.id),
        "user_id": str(workflow.user_id),
        "name": workflow.name,
        "description": workflow.description,
        "nodes_data": workflow.nodes_data or [],
        "edges_data": workflow.edges_data or [],
        "current_version": workflow.current_version,
        "is_published_api": workflow.is_published_api,
        "published_api_key": str(workflow.published_api_key)
        if workflow.published_api_key
        else None,
        "created_at": workflow.created_at.isoformat(),
        "updated_at": workflow.updated_at.isoformat(),
    }


@router.get("")
async def list_templates(
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, max_length=100),
    category: Optional[str] = Query(None),
    is_preset: Optional[bool] = Query(None),
    sort_by: str = Query("use_count", pattern="^(name|created_at|use_count)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
):
    service = TemplateService(db)
    result = await service.list_templates(
        page=page,
        page_size=page_size,
        keyword=keyword,
        category=category,
        is_preset=is_preset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return {"code": 0, "message": "success", "data": result.model_dump()}


@router.get("/{template_id}")
async def get_template(
    template_id: UUID,
    db: DBSession,
    user: CurrentUser,
):
    service = TemplateService(db)
    template = await service.get_template(template_id)
    data = TemplateDetailResponse.model_validate(template).model_dump()
    return {"code": 0, "message": "success", "data": data}


@router.post("/{template_id}/use")
async def use_template(
    template_id: UUID,
    body: UseTemplateRequest,
    db: DBSession,
    user: CurrentUser,
):
    service = TemplateService(db)
    workflow = await service.use_template(template_id, user.id, body.name)
    return {"code": 0, "message": "success", "data": _workflow_detail(workflow)}


@router.delete("/{template_id}")
async def delete_template(
    template_id: UUID,
    db: DBSession,
    user: CurrentUser,
):
    service = TemplateService(db)
    await service.delete_template(template_id, user.id)
    return {
        "code": 0,
        "message": "success",
        "data": {"message": "模板已删除", "template_id": str(template_id)},
    }
