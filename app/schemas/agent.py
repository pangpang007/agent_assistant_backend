import re
import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class AgentListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    keyword: Optional[str] = Field(default=None, max_length=100)
    is_preset: Optional[bool] = None


class AgentListItem(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model_id: Optional[uuid.UUID] = None
    model_name: Optional[str] = None
    memory_strategy: str
    output_format: str
    temperature: float
    max_tokens: int
    is_preset: bool
    tool_count: int = 0
    created_at: datetime
    updated_at: datetime


class AgentListResponse(BaseModel):
    items: list[AgentListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class AgentToolBrief(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    tool_type: str


class AgentDetailResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model_id: Optional[uuid.UUID] = None
    model_info: Optional[dict] = None
    memory_strategy: str
    output_format: str
    temperature: float
    max_tokens: int
    is_preset: bool
    tools: list[AgentToolBrief] = []
    knowledge_base_ids: list[uuid.UUID] = []
    created_at: datetime
    updated_at: datetime


class AgentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    system_prompt: Optional[str] = Field(default=None, max_length=50000)
    model_id: Optional[uuid.UUID] = None
    memory_strategy: str = Field(default="none", pattern="^(none|window|summary)$")
    output_format: str = Field(default="markdown", pattern="^(json|markdown|text)$")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=128000)
    tool_ids: list[uuid.UUID] = Field(default_factory=list)
    knowledge_base_ids: list[uuid.UUID] = Field(default_factory=list)


class AgentCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    message: str = "Agent 创建成功"


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    system_prompt: Optional[str] = Field(default=None, max_length=50000)
    model_id: Optional[uuid.UUID] = None
    memory_strategy: Optional[str] = Field(
        default=None, pattern="^(none|window|summary)$"
    )
    output_format: Optional[str] = Field(
        default=None, pattern="^(json|markdown|text)$"
    )
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=128000)
    tool_ids: Optional[list[uuid.UUID]] = None
    knowledge_base_ids: Optional[list[uuid.UUID]] = None


class AgentUpdateResponse(BaseModel):
    id: uuid.UUID
    name: str
    message: str = "Agent 更新成功"


class AgentDeleteResponse(BaseModel):
    message: str = "Agent 已删除"
    agent_id: uuid.UUID


class AgentCopyRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)


class AgentCopyResponse(BaseModel):
    id: uuid.UUID
    name: str
    original_id: uuid.UUID
    message: str = "Agent 复制成功"
