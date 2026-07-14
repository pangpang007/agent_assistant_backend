from datetime import datetime
from typing import Optional

from pydantic import AliasChoices, BaseModel, Field


class PublishApiRequest(BaseModel):
    pass


class PublishApiResponse(BaseModel):
    workflow_id: str
    api_key: str
    endpoint_url: str
    created_at: datetime


class UnpublishApiResponse(BaseModel):
    message: str = "已取消发布"
    workflow_id: str


class ResetApiKeyResponse(BaseModel):
    workflow_id: str
    api_key: str
    endpoint_url: str
    message: str = "API Key 已重置"


class PublishedApiItem(BaseModel):
    workflow_id: str
    workflow_name: str
    endpoint_url: str
    api_key_masked: str
    created_at: datetime
    call_count: int
    success_rate: float
    avg_duration_ms: Optional[int] = None
    is_active: bool


class PublishedApiListResponse(BaseModel):
    items: list[PublishedApiItem]
    total: int


class TogglePublishedApiRequest(BaseModel):
    """is_active / enabled / active 均可；省略则由服务端翻转当前状态。"""

    is_active: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices("is_active", "enabled", "active"),
    )


class TogglePublishedApiResponse(BaseModel):
    workflow_id: str
    is_active: bool
    message: str
