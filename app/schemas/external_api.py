from typing import Any, Optional

from pydantic import BaseModel, Field


class ExternalApiRunRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class ExternalApiRunResponse(BaseModel):
    execution_id: str
    status: str
    output: Optional[dict[str, Any]] = None
    duration_ms: int
    error: Optional[str] = None
