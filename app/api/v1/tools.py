import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.tool import ToolCreateRequest, ToolTestRequest, ToolUpdateRequest
from app.services.tool_service import ToolService

router = APIRouter()


@router.get("")
async def list_tools(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=100),
    tool_type: str | None = Query(None, pattern="^(preset|custom)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ToolService.list_tools(
        db=db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        keyword=keyword,
        tool_type=tool_type,
    )
    return {"code": 0, "message": "success", "data": data}


@router.get("/{tool_id}")
async def get_tool(
    tool_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ToolService.get_tool_detail(
        db=db, tool_id=tool_id, current_user=current_user
    )
    return {"code": 0, "message": "success", "data": data}


@router.post("")
async def create_tool(
    body: ToolCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tool = await ToolService.create_tool(
        db=db, user_id=current_user.id, data=body.model_dump()
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": str(tool.id),
            "name": tool.name,
            "message": "工具创建成功",
        },
    }


@router.put("/{tool_id}")
async def update_tool(
    tool_id: uuid.UUID,
    body: ToolUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tool = await ToolService.update_tool(
        db=db,
        tool_id=tool_id,
        current_user=current_user,
        data=body.model_dump(exclude_unset=True),
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": str(tool.id),
            "name": tool.name,
            "message": "工具更新成功",
        },
    }


@router.delete("/{tool_id}")
async def delete_tool(
    tool_id: uuid.UUID,
    force: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ToolService.delete_tool(
        db=db,
        tool_id=tool_id,
        current_user=current_user,
        force=force,
    )
    return {"code": 0, "message": "success", "data": data}


@router.post("/{tool_id}/test")
async def test_tool(
    tool_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    body: Optional[ToolTestRequest] = Body(default=None),
):
    req = body or ToolTestRequest()
    data = await ToolService.test_tool(
        db=db,
        tool_id=tool_id,
        current_user=current_user,
        parameters=req.parameters,
        timeout=req.timeout,
    )
    return {"code": 0, "message": "success", "data": data}
