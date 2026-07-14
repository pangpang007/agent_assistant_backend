from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class DashboardStatsResponse(BaseModel):
    workflow_count: int
    agent_count: int
    knowledge_base_count: int
    execution_count_this_month: int
    success_rate_this_month: float


class TokenUsageItem(BaseModel):
    date: date
    total_tokens: int
    total_cost: float


class TokenUsageResponse(BaseModel):
    items: list[TokenUsageItem]
    total_tokens: int
    total_cost: float


class RecentWorkflowItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    node_count: int = 0
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecentExecutionItem(BaseModel):
    id: str
    workflow_id: str
    workflow_name: Optional[str] = None
    status: str
    source: str = "web"
    total_duration_ms: Optional[int] = None
    started_at: datetime

    model_config = {"from_attributes": True}
