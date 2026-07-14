"""API Key generation, masking, hashing, and workflow resolution."""

from __future__ import annotations

import hashlib
import secrets
from typing import Optional
from uuid import UUID

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import (
    ApiDisabledError,
    ApiKeyMissingError,
    InvalidApiKeyError,
)
from app.core.redis import get_redis
from app.models.workflow import Workflow

API_KEY_PREFIX = "sk-"
API_KEY_LENGTH = 32

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def generate_api_key() -> str:
    """Generate API Key: sk- + 32 hex chars (from secrets.token_hex(16))."""
    prefix = settings.api_key_prefix or API_KEY_PREFIX
    random_part = secrets.token_hex(16)
    return f"{prefix}{random_part}"


def mask_api_key(api_key: Optional[str]) -> str:
    """Mask key as sk-xxxx...yyyy (e.g. sk-a1b2...o5p6)."""
    if not api_key or len(api_key) < 10:
        return "****"
    # Docs example: sk-a1b2...o5p6 → first 7 + ... + last 4
    return f"{api_key[:7]}...{api_key[-4:]}"


def hash_api_key(api_key: str) -> str:
    """SHA-256 hash truncated to 32 chars for Redis cache keys."""
    return hashlib.sha256(api_key.encode()).hexdigest()[:32]


async def resolve_workflow_by_api_key(
    db: AsyncSession,
    api_key: str,
) -> Workflow:
    """Look up an active published workflow by API key (with Redis cache)."""
    if not api_key:
        raise ApiKeyMissingError()

    redis = None
    cache_key = f"api_key:{hash_api_key(api_key)}"
    try:
        redis = get_redis()
        cached_wf_id = await redis.get(cache_key)
        if cached_wf_id:
            result = await db.execute(
                select(Workflow).where(
                    Workflow.id == UUID(cached_wf_id),
                    Workflow.is_published_api.is_(True),
                    Workflow.api_is_active.is_(True),
                )
            )
            workflow = result.scalar_one_or_none()
            if workflow and workflow.published_api_key == api_key:
                return workflow
            await redis.delete(cache_key)
    except Exception:
        pass

    result = await db.execute(
        select(Workflow).where(
            Workflow.published_api_key == api_key,
            Workflow.is_published_api.is_(True),
        )
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise InvalidApiKeyError()

    if not workflow.api_is_active:
        raise ApiDisabledError()

    try:
        if redis is None:
            redis = get_redis()
        await redis.setex(cache_key, settings.api_key_cache_ttl, str(workflow.id))
    except Exception:
        pass

    return workflow


async def get_workflow_by_api_key(
    request: Request,
    api_key: str,
    db: AsyncSession = Depends(get_db),
    header_key: str | None = Security(api_key_header),
) -> Workflow:
    """
    Resolve workflow for external runs.

    Path ``api_key`` is primary. If ``X-API-Key`` is present it must match.
    """
    effective_key = api_key
    if not effective_key:
        if header_key:
            effective_key = header_key
        else:
            raise ApiKeyMissingError()

    if header_key and header_key != effective_key:
        raise InvalidApiKeyError()

    workflow = await resolve_workflow_by_api_key(db, effective_key)
    request.state.workflow = workflow
    request.state.api_key = effective_key
    return workflow
