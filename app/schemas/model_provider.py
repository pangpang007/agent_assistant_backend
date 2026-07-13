import re
import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.transport_crypto import SensitiveStr


class ProviderListItem(BaseModel):
    id: uuid.UUID
    provider_name: str
    provider_type: str
    base_url: Optional[str] = None
    api_key_masked: str
    is_enabled: bool
    model_count: int = 0
    enabled_model_count: int = 0
    has_default_model: bool = False
    created_at: datetime


class ProviderListResponse(BaseModel):
    items: list[ProviderListItem]


class ProviderCreateRequest(BaseModel):
    provider_name: str = Field(..., min_length=1, max_length=100)
    provider_type: str = Field(..., pattern="^(openai|anthropic|google|custom)$")
    api_key: SensitiveStr = Field(..., min_length=1, max_length=1024)
    base_url: Optional[str] = Field(default=None, max_length=2048)
    models: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_custom_base_url(self):
        if self.provider_type == "custom" and not self.base_url:
            raise ValueError("自定义供应商必须提供 base_url")
        return self


class ProviderCreateResponse(BaseModel):
    id: uuid.UUID
    provider_name: str
    provider_type: str
    message: str = "供应商添加成功"


class ProviderUpdateRequest(BaseModel):
    provider_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    api_key: Optional[SensitiveStr] = Field(default=None, min_length=1, max_length=1024)
    base_url: Optional[str] = Field(default=None, max_length=2048)


class ProviderDeleteResponse(BaseModel):
    message: str = "供应商已删除"
    provider_id: uuid.UUID
    affected_models: int


class ProviderToggleResponse(BaseModel):
    id: uuid.UUID
    provider_name: str
    is_enabled: bool
    message: str


class ModelItem(BaseModel):
    id: uuid.UUID
    provider_id: uuid.UUID
    model_name: str
    display_name: Optional[str] = None
    input_price: float
    output_price: float
    is_enabled: bool
    is_default: bool
    created_at: datetime


class ModelListResponse(BaseModel):
    items: list[ModelItem]
    provider_name: str
    provider_type: str


class ModelCreateRequest(BaseModel):
    model_name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = Field(default=None, max_length=200)
    input_price: float = Field(default=0.0, ge=0.0)
    output_price: float = Field(default=0.0, ge=0.0)

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9.\-_]+$", v):
            raise ValueError("模型名称仅支持字母、数字、连字符、点和下划线")
        return v


class ModelCreateResponse(BaseModel):
    id: uuid.UUID
    model_name: str
    message: str = "模型添加成功"


class ModelUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=200)
    input_price: Optional[float] = Field(default=None, ge=0.0)
    output_price: Optional[float] = Field(default=None, ge=0.0)
    is_enabled: Optional[bool] = None


class ModelDeleteResponse(BaseModel):
    message: str = "模型已删除"
    model_id: uuid.UUID


class SetDefaultModelResponse(BaseModel):
    model_id: uuid.UUID
    model_name: str
    message: str = "已设为默认模型"


class UsageQueryParams(BaseModel):
    group_by: str = Field(default="day", pattern="^(model|day|provider)$")
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    provider_id: Optional[uuid.UUID] = None
    model_id: Optional[uuid.UUID] = None


class UsageItem(BaseModel):
    group_key: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float


class UsageSummary(BaseModel):
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cost: float
    date_range: str


class UsageResponse(BaseModel):
    items: list[UsageItem]
    summary: UsageSummary
