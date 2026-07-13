"""用户相关 Schema"""

import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    avatar_url: Optional[str] = None
    account_type: str
    team_id: Optional[uuid.UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserProfileResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    avatar_url: Optional[str] = None
    account_type: str
    team_id: Optional[uuid.UUID] = None
    team: Optional[dict] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    username: Optional[str] = Field(default=None, min_length=2, max_length=100)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r"^[\w\u4e00-\u9fff\-]+$", v):
            raise ValueError("用户名仅支持中英文、数字、下划线和短横线")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("用户名不能以短横线开头或结尾")
        return v
