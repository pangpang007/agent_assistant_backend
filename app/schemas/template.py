import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class SaveAsTemplateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    category: str = Field(default="自定义", max_length=100)
    thumbnail_url: Optional[str] = None


class UseTemplateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)


class TemplateListItem(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    category: str
    thumbnail_url: Optional[str] = None
    use_count: int
    node_count: int = 0
    is_preset: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TemplateListResponse(BaseModel):
    items: list[TemplateListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class TemplateDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    category: str
    thumbnail_url: Optional[str] = None
    use_count: int
    is_preset: bool
    nodes_data: Optional[list[Any]] = None
    edges_data: Optional[list[Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TemplateDeleteResponse(BaseModel):
    message: str = "模板已删除"
    template_id: uuid.UUID
