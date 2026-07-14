"""Dashboard statistics service."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.agent import Agent
from app.models.enums import ExecutionStatus
from app.models.execution import Execution
from app.models.knowledge import KnowledgeBase
from app.models.model_provider import ModelUsage
from app.models.workflow import Workflow


async def _redis_get(key: str):
    try:
        from app.core.redis import get_redis

        return await get_redis().get(key)
    except Exception:
        return None


async def _redis_setex(key: str, ttl: int, value: str) -> None:
    try:
        from app.core.redis import get_redis

        await get_redis().setex(key, ttl, value)
    except Exception:
        pass


class DashboardService:
    async def get_stats(self, db: AsyncSession, user_id: str) -> dict:
        cache_key = f"dashboard:stats:{user_id}"
        cached = await _redis_get(cache_key)
        if cached:
            return json.loads(cached)

        uid = UUID(user_id) if isinstance(user_id, str) else user_id
        month_start = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        workflow_count = (
            await db.execute(
                select(func.count(Workflow.id)).where(Workflow.user_id == uid)
            )
        ).scalar() or 0

        # User agents + presets (is_preset / null user_id presets)
        agent_count = (
            await db.execute(
                select(func.count(Agent.id)).where(
                    or_(Agent.user_id == uid, Agent.is_preset.is_(True))
                )
            )
        ).scalar() or 0

        kb_count = (
            await db.execute(
                select(func.count(KnowledgeBase.id)).where(
                    KnowledgeBase.user_id == uid
                )
            )
        ).scalar() or 0

        # Executions have no user_id — JOIN workflows
        exec_base = and_(
            Workflow.user_id == uid,
            Execution.started_at >= month_start,
            Execution.status.in_(
                [ExecutionStatus.success, ExecutionStatus.failed]
            ),
        )

        exec_count = (
            await db.execute(
                select(func.count(Execution.id))
                .select_from(Execution)
                .join(Workflow, Workflow.id == Execution.workflow_id)
                .where(exec_base)
            )
        ).scalar() or 0

        success_count = (
            await db.execute(
                select(func.count(Execution.id))
                .select_from(Execution)
                .join(Workflow, Workflow.id == Execution.workflow_id)
                .where(
                    exec_base,
                    Execution.status == ExecutionStatus.success,
                )
            )
        ).scalar() or 0

        success_rate = (
            round((success_count / exec_count * 100), 1) if exec_count > 0 else 0.0
        )

        data = {
            "workflow_count": workflow_count,
            "agent_count": agent_count,
            "knowledge_base_count": kb_count,
            "execution_count_this_month": exec_count,
            "success_rate_this_month": success_rate,
        }

        await _redis_setex(
            cache_key, settings.dashboard_cache_ttl, json.dumps(data, default=str)
        )
        return data

    async def get_token_usage(
        self, db: AsyncSession, user_id: str, days: int = 7
    ) -> dict:
        cache_key = f"dashboard:token_usage:{user_id}:{days}"
        cached = await _redis_get(cache_key)
        if cached:
            return json.loads(cached)

        uid = UUID(user_id) if isinstance(user_id, str) else user_id
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        result = await db.execute(
            select(
                ModelUsage.date,
                func.sum(ModelUsage.input_tokens + ModelUsage.output_tokens).label(
                    "total_tokens"
                ),
                func.sum(ModelUsage.cost).label("total_cost"),
            )
            .where(
                and_(
                    ModelUsage.user_id == uid,
                    ModelUsage.date >= start_date,
                    ModelUsage.date <= end_date,
                )
            )
            .group_by(ModelUsage.date)
            .order_by(ModelUsage.date.asc())
        )
        rows = result.all()
        data_map = {
            row.date: {
                "total_tokens": int(row.total_tokens or 0),
                "total_cost": float(row.total_cost or 0),
            }
            for row in rows
        }

        items = []
        total_tokens = 0
        total_cost = 0.0
        current = start_date
        while current <= end_date:
            day_data = data_map.get(
                current, {"total_tokens": 0, "total_cost": 0.0}
            )
            items.append(
                {
                    "date": current.isoformat(),
                    "total_tokens": day_data["total_tokens"],
                    "total_cost": round(day_data["total_cost"], 6),
                }
            )
            total_tokens += day_data["total_tokens"]
            total_cost += day_data["total_cost"]
            current += timedelta(days=1)

        response = {
            "items": items,
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 6),
        }
        await _redis_setex(
            cache_key,
            settings.dashboard_cache_ttl,
            json.dumps(response, default=str),
        )
        return response

    async def get_recent_workflows(
        self, db: AsyncSession, user_id: str, limit: int = 5
    ) -> list[dict]:
        uid = UUID(user_id) if isinstance(user_id, str) else user_id
        result = await db.execute(
            select(Workflow)
            .where(Workflow.user_id == uid)
            .order_by(Workflow.updated_at.desc())
            .limit(limit)
        )
        workflows = result.scalars().all()
        return [
            {
                "id": str(wf.id),
                "name": wf.name,
                "description": wf.description,
                "node_count": len(wf.nodes_data) if wf.nodes_data else 0,
                "updated_at": wf.updated_at,
            }
            for wf in workflows
        ]

    async def get_recent_executions(
        self, db: AsyncSession, user_id: str, limit: int = 5
    ) -> list[dict]:
        uid = UUID(user_id) if isinstance(user_id, str) else user_id
        result = await db.execute(
            select(
                Execution.id,
                Execution.workflow_id,
                Workflow.name.label("workflow_name"),
                Execution.status,
                Execution.source,
                Execution.total_duration_ms,
                Execution.started_at,
            )
            .select_from(Execution)
            .join(Workflow, Workflow.id == Execution.workflow_id)
            .where(Workflow.user_id == uid)
            .order_by(Execution.started_at.desc())
            .limit(limit)
        )
        rows = result.all()
        return [
            {
                "id": str(row.id),
                "workflow_id": str(row.workflow_id),
                "workflow_name": row.workflow_name,
                "status": row.status.value
                if hasattr(row.status, "value")
                else str(row.status),
                "source": row.source or "web",
                "total_duration_ms": row.total_duration_ms,
                "started_at": row.started_at,
            }
            for row in rows
        ]
