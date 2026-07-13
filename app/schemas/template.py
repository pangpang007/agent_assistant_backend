import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TemplateCreate(BaseModel):
    workflow_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    category: str = Field(..., min_length=1, max_length=100)
    thumbnail_url: Optional[str] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = None
    thumbnail_url: Optional[str] = None


class TemplateResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    name: str
    description: Optional[str] = None
    category: str
    thumbnail_url: Optional[str] = None
    use_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
