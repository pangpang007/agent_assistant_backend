"""工作流管理路由。"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import VersionNotFoundError
from app.core.redis import get_redis
from app.models.user import User
from app.schemas.workflow import (
    NodeTestRequest,
    TagVersionRequest,
    ValidationResultResponse,
    WorkflowCreate,
    WorkflowImportRequest,
    WorkflowUpdate,
)
from app.schemas.execution import WorkflowRunRequest
from app.schemas.template import SaveAsTemplateRequest, TemplateDetailResponse
from app.services.execution_service import ExecutionService
from app.services.node_test_service import NodeTestService
from app.services.template_service import TemplateService
from app.services.validation_service import ValidationService
from app.services.version_service import VersionService
from app.services.workflow_service import WorkflowService

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
async def list_workflows(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, max_length=100),
    sort_by: str = Query("updated_at", pattern="^(name|created_at|updated_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = WorkflowService(db)
    result = await service.list_workflows(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        keyword=keyword,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    result["items"] = [item.model_dump() for item in result["items"]]
    return {"code": 0, "message": "success", "data": result}


@router.post("")
async def create_workflow(
    body: WorkflowCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = WorkflowService(db)
    workflow = await service.create_workflow(
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        nodes_data=body.nodes_data,
        edges_data=body.edges_data,
    )
    return {"code": 0, "message": "success", "data": _workflow_detail(workflow)}


@router.post("/import")
async def import_workflow(
    body: WorkflowImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = WorkflowService(db)
    data = body.data.model_dump()
    workflow = await service.import_workflow(
        user_id=current_user.id,
        import_data=data,
        name_override=body.name,
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": str(workflow.id),
            "name": workflow.name,
            "message": "工作流导入成功",
        },
    }


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = WorkflowService(db)
    workflow = await service.get_workflow(workflow_id, current_user.id)
    return {"code": 0, "message": "success", "data": _workflow_detail(workflow)}


@router.put("/{workflow_id}")
async def update_workflow(
    workflow_id: uuid.UUID,
    body: WorkflowUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = WorkflowService(db)
    workflow = await service.get_workflow(workflow_id, current_user.id)
    workflow = await service.update_workflow(
        workflow,
        name=body.name,
        description=body.description,
        nodes_data=body.nodes_data,
        edges_data=body.edges_data,
    )
    return {"code": 0, "message": "success", "data": _workflow_detail(workflow)}


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = WorkflowService(db)
    await service.delete_workflow(workflow_id, current_user.id)
    return {
        "code": 0,
        "message": "success",
        "data": {"message": "工作流已删除", "workflow_id": str(workflow_id)},
    }


@router.get("/{workflow_id}/export")
async def export_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = WorkflowService(db)
    workflow = await service.get_workflow(workflow_id, current_user.id)
    data = await service.export_workflow(workflow)
    return {"code": 0, "message": "success", "data": data}


@router.get("/{workflow_id}/versions")
async def list_versions(
    workflow_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wf_service = WorkflowService(db)
    await wf_service.get_workflow(workflow_id, current_user.id)
    version_service = VersionService(db)
    result = await version_service.list_versions(workflow_id, page, page_size)
    result["items"] = [item.model_dump() for item in result["items"]]
    return {"code": 0, "message": "success", "data": result}


@router.get("/{workflow_id}/versions/{version_number}")
async def get_version(
    workflow_id: uuid.UUID,
    version_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wf_service = WorkflowService(db)
    await wf_service.get_workflow(workflow_id, current_user.id)
    version_service = VersionService(db)
    version = await version_service.get_version(workflow_id, version_number)
    if not version:
        raise VersionNotFoundError(version_number)
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": str(version.id),
            "workflow_id": str(version.workflow_id),
            "version_number": version.version_number,
            "tag": version.tag,
            "nodes_data": version.nodes_data or [],
            "edges_data": version.edges_data or [],
            "created_at": version.created_at.isoformat(),
        },
    }


@router.post("/{workflow_id}/versions/{version_number}/rollback")
async def rollback_version(
    workflow_id: uuid.UUID,
    version_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wf_service = WorkflowService(db)
    workflow = await wf_service.get_workflow(workflow_id, current_user.id)
    version_service = VersionService(db)
    result = await version_service.rollback_to_version(workflow, version_number)
    result["workflow_id"] = str(result["workflow_id"])
    return {"code": 0, "message": "success", "data": result}


@router.post("/{workflow_id}/versions/{version_number}/tag")
async def tag_version(
    workflow_id: uuid.UUID,
    version_number: int,
    body: TagVersionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    version_service = VersionService(db)
    result = await version_service.tag_version(
        workflow_id, version_number, body.tag, current_user.id
    )
    result["id"] = str(result["id"])
    result["workflow_id"] = str(result["workflow_id"])
    if result.get("created_at"):
        result["created_at"] = result["created_at"].isoformat()
    return {"code": 0, "message": "success", "data": result}


@router.delete("/{workflow_id}/versions/{version_number}/tag")
async def remove_tag(
    workflow_id: uuid.UUID,
    version_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    version_service = VersionService(db)
    result = await version_service.remove_tag(
        workflow_id, version_number, current_user.id
    )
    result["id"] = str(result["id"])
    result["workflow_id"] = str(result["workflow_id"])
    if result.get("created_at"):
        result["created_at"] = result["created_at"].isoformat()
    return {"code": 0, "message": "success", "data": result}


@router.get("/{workflow_id}/versions/diff")
async def diff_versions(
    workflow_id: uuid.UUID,
    v1: int = Query(..., ge=1),
    v2: int = Query(..., ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wf_service = WorkflowService(db)
    await wf_service.get_workflow(workflow_id, current_user.id)
    version_service = VersionService(db)
    diff = await version_service.diff_versions(workflow_id, v1, v2)
    return {"code": 0, "message": "success", "data": diff.model_dump()}


@router.post("/{workflow_id}/save-as-template")
async def save_as_template(
    workflow_id: uuid.UUID,
    body: SaveAsTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = TemplateService(db)
    template = await service.save_as_template(
        workflow_id=workflow_id,
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        category=body.category,
        thumbnail_url=body.thumbnail_url,
    )
    data = TemplateDetailResponse.model_validate(template).model_dump()
    return {"code": 0, "message": "success", "data": data}


@router.post("/{workflow_id}/validate")
async def validate_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wf_service = WorkflowService(db)
    workflow = await wf_service.get_workflow(workflow_id, current_user.id)
    issues = await ValidationService().validate_workflow(
        workflow.nodes_data or [], workflow.edges_data or []
    )
    error_count = sum(1 for i in issues if i.level == "error")
    warning_count = sum(1 for i in issues if i.level == "warning")
    result = ValidationResultResponse(
        is_valid=error_count == 0,
        error_count=error_count,
        warning_count=warning_count,
        issues=issues,
    )
    return {"code": 0, "message": "success", "data": result.model_dump()}


@router.post("/{workflow_id}/run")
async def run_workflow(
    workflow_id: uuid.UUID,
    body: WorkflowRunRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    redis = get_redis()
    service = ExecutionService(db, redis)
    execution = await service.start_execution(
        workflow_id=workflow_id,
        user_id=current_user.id,
        input_data=body.input_data,
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "execution_id": str(execution.id),
            "status": execution.status.value,
            "message": "工作流已开始执行",
        },
    }


@router.post("/{workflow_id}/nodes/test")
async def test_node(
    workflow_id: uuid.UUID,
    body: NodeTestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    redis = get_redis()
    service = NodeTestService(db, redis)
    result = await service.test_node(
        workflow_id=workflow_id,
        user_id=current_user.id,
        node_id=body.node_id,
        node_type=body.node_type,
        config=body.config,
        input_variables=body.input_variables,
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "output": result.output,
            "duration_ms": result.duration_ms,
            "tokens_used": result.tokens_used,
            "error": result.error,
        },
    }
