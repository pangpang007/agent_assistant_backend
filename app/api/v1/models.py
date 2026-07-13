import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.model_provider import (
    ModelCreateRequest,
    ModelUpdateRequest,
    ProviderCreateRequest,
    ProviderUpdateRequest,
)
from app.services.model_service import ModelService

router = APIRouter()


@router.get("/providers")
async def list_providers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await ModelService.list_providers(db=db, user_id=current_user.id)
    return {"code": 0, "message": "success", "data": {"items": items}}


@router.post("/providers")
async def create_provider(
    body: ProviderCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    provider = await ModelService.create_provider(
        db=db, user_id=current_user.id, data=body.model_dump()
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": str(provider.id),
            "provider_name": provider.provider_name,
            "provider_type": provider.provider_type,
            "message": "供应商添加成功",
        },
    }


@router.put("/providers/{provider_id}")
async def update_provider(
    provider_id: uuid.UUID,
    body: ProviderUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    provider = await ModelService.update_provider(
        db=db,
        provider_id=provider_id,
        current_user=current_user,
        data=body.model_dump(exclude_unset=True),
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": str(provider.id),
            "provider_name": provider.provider_name,
            "message": "供应商更新成功",
        },
    }


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ModelService.delete_provider(
        db=db, provider_id=provider_id, current_user=current_user
    )
    data["provider_id"] = str(data["provider_id"])
    return {"code": 0, "message": "success", "data": data}


@router.post("/providers/{provider_id}/toggle")
async def toggle_provider(
    provider_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ModelService.toggle_provider(
        db=db, provider_id=provider_id, current_user=current_user
    )
    data["id"] = str(data["id"])
    return {"code": 0, "message": "success", "data": data}


@router.get("/providers/{provider_id}/models")
async def list_models(
    provider_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ModelService.list_models(
        db=db, provider_id=provider_id, current_user=current_user
    )
    for item in data["items"]:
        item["id"] = str(item["id"])
        item["provider_id"] = str(item["provider_id"])
    return {"code": 0, "message": "success", "data": data}


@router.post("/providers/{provider_id}/models")
async def create_model(
    provider_id: uuid.UUID,
    body: ModelCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    model = await ModelService.create_model(
        db=db,
        provider_id=provider_id,
        current_user=current_user,
        data=body.model_dump(),
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": str(model.id),
            "model_name": model.model_name,
            "message": "模型添加成功",
        },
    }


@router.get("/usage")
async def get_usage(
    group_by: str = Query("day", pattern="^(model|day|provider)$"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    provider_id: uuid.UUID | None = Query(None),
    model_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ModelService.get_usage(
        db=db,
        user_id=current_user.id,
        group_by=group_by,
        start_date=start_date,
        end_date=end_date,
        provider_id=provider_id,
        model_id=model_id,
    )
    return {"code": 0, "message": "success", "data": data}


@router.put("/{model_id}")
async def update_model(
    model_id: uuid.UUID,
    body: ModelUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    model = await ModelService.update_model(
        db=db,
        model_id=model_id,
        current_user=current_user,
        data=body.model_dump(exclude_unset=True),
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": str(model.id),
            "model_name": model.model_name,
            "message": "模型更新成功",
        },
    }


@router.delete("/{model_id}")
async def delete_model(
    model_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await ModelService.delete_model(
        db=db, model_id=model_id, current_user=current_user
    )
    return {
        "code": 0,
        "message": "success",
        "data": {"message": "模型已删除", "model_id": str(model_id)},
    }


@router.post("/{model_id}/set-default")
async def set_default_model(
    model_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    model = await ModelService.set_default_model(
        db=db, model_id=model_id, current_user=current_user
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "model_id": str(model.id),
            "model_name": model.model_name,
            "message": "已设为默认模型",
        },
    }
