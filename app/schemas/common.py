from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """通用分页响应"""

    items: List[T]
    total: int
    page: int
    page_size: int
    has_next: bool


class ErrorResponse(BaseModel):
    """统一错误响应"""

    code: str
    message: str
    details: Optional[list] = None


class ErrorResponseWrapper(BaseModel):
    """错误响应包装"""

    error: ErrorResponse
