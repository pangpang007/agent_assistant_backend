import uuid
from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from app.core.config import settings
from app.core.transport_crypto import (
    decrypt_transport_field,
    is_transport_encrypted,
)


def _env_value_before(value: str | None) -> str | None:
    """若为 enc:v1:... 则解密；否则保留明文（string 类型允许明文）。"""
    if value is None:
        return None
    if is_transport_encrypted(value):
        return decrypt_transport_field(value)
    return value


OptionalTransportStr = Annotated[str, BeforeValidator(_env_value_before)]


class EnvVarCreateRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=255, pattern=r"^[A-Z0-9_]+$")
    value: OptionalTransportStr = Field(..., min_length=1, max_length=10000)
    type: str = Field(default="string", pattern="^(string|secret)$")

    @model_validator(mode="before")
    @classmethod
    def require_enc_for_secret(cls, data):
        if not isinstance(data, dict):
            return data
        if (
            settings.transport_require_encryption
            and data.get("type", "string") == "secret"
            and isinstance(data.get("value"), str)
            and not is_transport_encrypted(data["value"])
        ):
            raise ValueError("secret 类型 value 必须使用 enc:v1:... 加密传输")
        return data


class EnvVarUpdateRequest(BaseModel):
    value: Optional[OptionalTransportStr] = Field(
        default=None, min_length=1, max_length=10000
    )
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
