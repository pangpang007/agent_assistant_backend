import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EnvVariableCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=255, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    value: str = Field(..., min_length=1)
    type: str = Field(default="string", pattern="^(string|secret)$")


class EnvVariableUpdate(BaseModel):
    value: Optional[str] = Field(None, min_length=1)
    type: Optional[str] = Field(None, pattern="^(string|secret)$")


class EnvVariableResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    key: str
    type: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
