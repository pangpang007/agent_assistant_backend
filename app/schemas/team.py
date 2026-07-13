"""团队相关 Schema"""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class TeamCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class JoinTeamRequest(BaseModel):
    invite_code: str = Field(..., min_length=6, max_length=6)


class TeamResponse(BaseModel):
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    invite_code: str
    member_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TeamMemberResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    avatar_url: Optional[str] = None
    account_type: str
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class TeamMembersResponse(BaseModel):
    team_id: uuid.UUID
    team_name: str
    members: List[TeamMemberResponse]
    total: int
