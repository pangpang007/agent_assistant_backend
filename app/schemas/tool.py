import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.transport_crypto import decrypt_sensitive_dict_fields


class ToolListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    keyword: Optional[str] = Field(default=None, max_length=100)
    tool_type: Optional[str] = Field(default=None, pattern="^(preset|custom)$")


class ToolListItem(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    tool_type: str
    is_preset: bool
    agent_count: int = 0
    created_at: datetime
    updated_at: datetime


class ToolListResponse(BaseModel):
    items: list[ToolListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class ToolDetailResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    name: str
    description: Optional[str] = None
    tool_type: str
    is_preset: bool
    openapi_spec: Optional[dict] = None
    api_url: Optional[str] = None
    auth_type: str
    auth_config_summary: Optional[dict] = None
    agent_count: int = 0
    created_at: datetime
    updated_at: datetime


class ToolCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    api_url: str = Field(..., min_length=1, max_length=2048)
    openapi_spec: Optional[dict] = None
    auth_type: str = Field(default="none", pattern="^(none|api_key|bearer)$")
    auth_config: Optional[dict] = None

    @field_validator("api_url")
    @classmethod
    def validate_api_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("api_url 必须以 http:// 或 https:// 开头")
        return v

    @field_validator("auth_config")
    @classmethod
    def decrypt_auth_config(cls, v: dict | None) -> dict | None:
        return decrypt_sensitive_dict_fields(v, ("api_key_value", "token"))


class ToolCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    message: str = "工具创建成功"


class ToolUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    api_url: Optional[str] = Field(default=None, max_length=2048)
    openapi_spec: Optional[dict] = None
    auth_type: Optional[str] = Field(default=None, pattern="^(none|api_key|bearer)$")
    auth_config: Optional[dict] = None

    @field_validator("auth_config")
    @classmethod
    def decrypt_auth_config(cls, v: dict | None) -> dict | None:
        return decrypt_sensitive_dict_fields(v, ("api_key_value", "token"))


class ToolDeleteResponse(BaseModel):
    message: str
    agent_count: int
    deleted: bool


class ToolTestRequest(BaseModel):
    parameters: dict = Field(..., description="工具调用参数")
    timeout: int = Field(default=30, ge=1, le=60)


class ToolTestResponse(BaseModel):
    success: bool
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None
