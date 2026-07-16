"""认证相关 Schema"""

import re

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.transport_crypto import SensitiveStr


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=2, max_length=100)
    password: SensitiveStr = Field(..., min_length=8, max_length=128)
    account_type: str = Field(default="personal", pattern="^(personal|team)$")
    team_name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[\w\u4e00-\u9fff\-]+$", v):
            raise ValueError("用户名仅支持中英文、数字、下划线和短横线")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("用户名不能以短横线开头或结尾")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码必须包含至少一个大写字母")
        if not re.search(r"[a-z]", v):
            raise ValueError("密码必须包含至少一个小写字母")
        if not re.search(r"[0-9]", v):
            raise ValueError("密码必须包含至少一个数字")
        return v

    @field_validator("team_name")
    @classmethod
    def validate_team_name(cls, v, info):
        account_type = info.data.get("account_type")
        if account_type == "team" and not v:
            raise ValueError("团队注册时必须提供 team_name")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: SensitiveStr = Field(..., min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class TokenStatusResponse(BaseModel):
    is_valid: bool
    user_id: str | None = None
    access_token_expires_at: int | None = None
    access_token_remaining_seconds: int | None = None
    access_token_needs_refresh: bool = False
    refresh_token_valid: bool = False
    refresh_token_expires_at: int | None = None


class ChangePasswordRequest(BaseModel):
    old_password: SensitiveStr = Field(..., min_length=1)
    new_password: SensitiveStr = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码必须包含至少一个大写字母")
        if not re.search(r"[a-z]", v):
            raise ValueError("密码必须包含至少一个小写字母")
        if not re.search(r"[0-9]", v):
            raise ValueError("密码必须包含至少一个数字")
        return v
