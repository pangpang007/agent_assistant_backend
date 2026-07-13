import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ========== KnowledgeBase Schemas ==========

class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    embedding_model: str = Field(default="text-embedding-3-small", max_length=100)
    chunk_size: int = Field(default=512, ge=100, le=10000)
    chunk_overlap: int = Field(default=50, ge=0, le=2000)


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)


class KnowledgeBaseConfigUpdate(BaseModel):
    """更新分块配置"""

    chunk_size: int = Field(..., ge=100, le=10000)
    chunk_overlap: int = Field(..., ge=0, le=2000)

    @model_validator(mode="after")
    def validate_overlap(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        return self


class KnowledgeBaseResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: Optional[str] = None
    document_count: int = 0
    total_size: int = 0
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeBaseListItem(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    document_count: int = 0
    total_size: int = 0
    embedding_model: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeBaseListResponse(BaseModel):
    items: list[KnowledgeBaseListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


# ========== KnowledgeDocument Schemas ==========

class KnowledgeDocumentResponse(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    filename: str
    file_size: int
    file_type: str
    chunk_count: int
    token_count: int = 0
    status: str
    error_message: Optional[str] = None
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeDocumentStatusResponse(BaseModel):
    """文档处理状态响应（用于轮询）"""
    id: uuid.UUID
    status: str
    chunk_count: int = 0
    token_count: int = 0
    error_message: Optional[str] = None
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None


class KnowledgeDocumentListResponse(BaseModel):
    items: list[KnowledgeDocumentResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


# ========== Search Schemas ==========

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResultItem(BaseModel):
    chunk_id: str
    content: str
    chunk_index: int
    token_count: int
    document_id: str
    filename: str
    score: float


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResultItem]
