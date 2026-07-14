import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EnvVarCreateRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=255, pattern=r"^[A-Z0-9_]+$")
    value: str = Field(..., min_length=1, max_length=10000)
    type: str = Field(default="string", pattern="^(string|secret)$")


class EnvVarUpdateRequest(BaseModel):
    value: Optional[str] = Field(default=None, min_length=1, max_length=10000)
    type: Optional[str] = Field(default=None, pattern="^(string|secret)$")


class EnvVarListItem(BaseModel):
    id: uuid.UUID
    key: str
    type: str
    value: Optional[str] = None
    masked_value: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EnvVarListResponse(BaseModel):
    items: list[EnvVarListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class EnvVarResponse(BaseModel):
    id: uuid.UUID
    key: str
    type: str
    value: Optional[str] = None
    masked_value: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EnvVarDeleteResponse(BaseModel):
    message: str = "环境变量已删除"
    env_var_id: uuid.UUID


# Legacy aliases
EnvVariableCreate = EnvVarCreateRequest
EnvVariableUpdate = EnvVarUpdateRequest
EnvVariableResponse = EnvVarResponse
