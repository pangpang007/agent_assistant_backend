"""Workflow publish-as-API service."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_key_auth import generate_api_key, mask_api_key
from app.core.exceptions import (
    EmptyWorkflowError,
    ForbiddenException,
    NotPublishedError,
    WorkflowNotFoundError,
)
from app.models.workflow import Workflow
from app.services.cache_invalidator import CacheInvalidator


class PublishApiService:
    async def publish_api(
        self, db: AsyncSession, user_id: str, workflow_id: str
    ) -> dict:
        workflow = await self._get_workflow_or_404(db, user_id, workflow_id)

        if workflow.is_published_api and workflow.published_api_key:
            return {
                "workflow_id": str(workflow.id),
                "api_key": workflow.published_api_key,
                "endpoint_url": f"/api/published/{workflow.published_api_key}/run",
                "created_at": workflow.updated_at or workflow.created_at,
            }

        if not workflow.nodes_data or len(workflow.nodes_data) == 0:
            raise EmptyWorkflowError()

        api_key = generate_api_key()
        workflow.is_published_api = True
        workflow.published_api_key = api_key
        workflow.api_is_active = True
        workflow.api_call_count = 0
        workflow.api_total_duration_ms = 0
        workflow.api_success_count = 0

        await db.flush()
        await CacheInvalidator.invalidate_dashboard(user_id)

        return {
            "workflow_id": str(workflow.id),
            "api_key": api_key,
            "endpoint_url": f"/api/published/{api_key}/run",
            "created_at": datetime.now(timezone.utc),
        }

    async def unpublish_api(
        self, db: AsyncSession, user_id: str, workflow_id: str
    ) -> dict:
        workflow = await self._get_workflow_or_404(db, user_id, workflow_id)

        if not workflow.is_published_api:
            raise NotPublishedError()

        if workflow.published_api_key:
            await CacheInvalidator.invalidate_api_key(workflow.published_api_key)

        workflow.is_published_api = False
        workflow.published_api_key = None
        await db.flush()
        await CacheInvalidator.invalidate_dashboard(user_id)

        return {"message": "已取消发布", "workflow_id": str(workflow.id)}

    async def reset_api_key(
        self, db: AsyncSession, user_id: str, workflow_id: str
    ) -> dict:
        workflow = await self._get_workflow_or_404(db, user_id, workflow_id)

        if not workflow.is_published_api:
            raise NotPublishedError()

        if workflow.published_api_key:
            await CacheInvalidator.invalidate_api_key(workflow.published_api_key)

        new_api_key = generate_api_key()
        workflow.published_api_key = new_api_key
        await db.flush()

        return {
            "workflow_id": str(workflow.id),
            "api_key": new_api_key,
            "endpoint_url": f"/api/published/{new_api_key}/run",
            "message": "API Key 已重置",
        }

    async def list_published_apis(self, db: AsyncSession, user_id: str) -> dict:
        uid = UUID(user_id) if isinstance(user_id, str) else user_id
        result = await db.execute(
            select(Workflow)
            .where(
                and_(
                    Workflow.user_id == uid,
                    Workflow.is_published_api.is_(True),
                )
            )
            .order_by(Workflow.created_at.desc())
        )
        workflows = result.scalars().all()

        items = []
        for wf in workflows:
            call_count = wf.api_call_count or 0
            success_count = wf.api_success_count or 0
            total_duration = wf.api_total_duration_ms or 0
            masked = mask_api_key(wf.published_api_key)
            success_rate = (
                round(success_count / call_count * 100, 1) if call_count > 0 else 0.0
            )
            avg_duration = (
                round(total_duration / call_count) if call_count > 0 else None
            )
            items.append(
                {
                    "workflow_id": str(wf.id),
                    "workflow_name": wf.name,
                    "endpoint_url": f"/api/published/{masked}/run",
                    "api_key_masked": masked,
                    "created_at": wf.created_at,
                    "call_count": call_count,
                    "success_rate": success_rate,
                    "avg_duration_ms": avg_duration,
                    "is_active": bool(wf.api_is_active),
                }
            )

        return {"items": items, "total": len(items)}

    async def toggle_api(
        self, db: AsyncSession, user_id: str, workflow_id: str, is_active: bool
    ) -> dict:
        workflow = await self._get_workflow_or_404(db, user_id, workflow_id)

        if not workflow.is_published_api:
            raise NotPublishedError()

        workflow.api_is_active = is_active
        if not is_active and workflow.published_api_key:
            await CacheInvalidator.invalidate_api_key(workflow.published_api_key)

        await db.flush()
        status_text = "已启用" if is_active else "已停用"
        return {
            "workflow_id": str(workflow.id),
            "is_active": is_active,
            "message": f"API {status_text}",
        }

    async def _get_workflow_or_404(
        self, db: AsyncSession, user_id: str, workflow_id: str
    ) -> Workflow:
        try:
            wid = UUID(workflow_id) if isinstance(workflow_id, str) else workflow_id
        except ValueError:
            raise WorkflowNotFoundError()

        result = await db.execute(select(Workflow).where(Workflow.id == wid))
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise WorkflowNotFoundError()

        if str(workflow.user_id) != str(user_id):
            raise ForbiddenException("无权限操作此工作流")

        return workflow
