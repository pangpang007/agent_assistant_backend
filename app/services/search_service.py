"""Global search across workflows, agents, knowledge bases, templates."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.agent import Agent
from app.models.knowledge import KnowledgeBase
from app.models.template import Template
from app.models.workflow import Workflow


def compute_search_score(name: str, query: str) -> float:
    """Pure relevance score for unit tests / ILIKE fallback ranking."""
    if not name or not query:
        return 0.0
    name_l = name.lower()
    q_l = query.lower().strip()
    if not q_l:
        return 0.0
    if name_l == q_l:
        return 1.0
    if name_l.startswith(q_l):
        return 0.8
    if q_l in name_l:
        return 0.5
    return 0.1


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


class SearchService:
    MAX_PER_TYPE = 5

    async def search(
        self,
        db: AsyncSession,
        user_id: str,
        query: str,
        search_type: str | None = None,
    ) -> dict:
        q_hash = hashlib.sha256(
            f"{query}:{search_type or 'all'}".encode()
        ).hexdigest()[:16]
        cache_key = f"search:{user_id}:{q_hash}"
        cached = await _redis_get(cache_key)
        if cached:
            return json.loads(cached)

        results: dict = {
            "workflows": [],
            "agents": [],
            "knowledge_bases": [],
            "templates": [],
        }
        keyword = f"%{query}%"
        limit = self.MAX_PER_TYPE

        if search_type is None or search_type == "workflow":
            results["workflows"] = await self._search_workflows(
                db, user_id, keyword, query, limit
            )
        if search_type is None or search_type == "agent":
            results["agents"] = await self._search_agents(
                db, user_id, keyword, query, limit
            )
        if search_type is None or search_type == "knowledge":
            results["knowledge_bases"] = await self._search_knowledge_bases(
                db, user_id, keyword, query, limit
            )
        if search_type is None or search_type == "template":
            results["templates"] = await self._search_templates(
                db, user_id, keyword, query, limit
            )

        payload = {
            "query": query,
            **results,
            "total": sum(len(v) for v in results.values()),
        }
        await _redis_setex(
            cache_key, settings.search_cache_ttl, json.dumps(payload, default=str)
        )
        return payload

    async def _search_workflows(self, db, user_id, keyword, query, limit):
        uid = UUID(user_id) if isinstance(user_id, str) else user_id
        try:
            stmt = (
                select(
                    Workflow.id,
                    Workflow.name,
                    Workflow.description,
                    func.similarity(Workflow.name, query).label("sim"),
                )
                .where(
                    and_(
                        Workflow.user_id == uid,
                        or_(
                            Workflow.name.ilike(keyword),
                            Workflow.description.ilike(keyword),
                        ),
                    )
                )
                .order_by(func.similarity(Workflow.name, query).desc())
                .limit(limit)
            )
            result = await db.execute(stmt)
            rows = result.all()
            return [
                {
                    "id": str(row.id),
                    "name": row.name,
                    "description": row.description,
                    "type": "workflow",
                    "score": float(row.sim) if row.sim is not None else 0.0,
                }
                for row in rows
            ]
        except Exception:
            await db.rollback()
            return await self._search_workflows_ilike(db, uid, keyword, query, limit)

    async def _search_workflows_ilike(self, db, uid, keyword, query, limit):
        result = await db.execute(
            select(Workflow.id, Workflow.name, Workflow.description)
            .where(
                and_(
                    Workflow.user_id == uid,
                    or_(
                        Workflow.name.ilike(keyword),
                        Workflow.description.ilike(keyword),
                    ),
                )
            )
            .limit(limit * 3)
        )
        items = [
            {
                "id": str(row.id),
                "name": row.name,
                "description": row.description,
                "type": "workflow",
                "score": compute_search_score(row.name, query),
            }
            for row in result.all()
        ]
        items.sort(key=lambda x: x["score"], reverse=True)
        return items[:limit]

    async def _search_agents(self, db, user_id, keyword, query, limit):
        uid = UUID(user_id) if isinstance(user_id, str) else user_id
        ownership = or_(Agent.user_id == uid, Agent.is_preset.is_(True))
        try:
            stmt = (
                select(
                    Agent.id,
                    Agent.name,
                    Agent.description,
                    func.similarity(Agent.name, query).label("sim"),
                )
                .where(
                    and_(
                        ownership,
                        or_(
                            Agent.name.ilike(keyword),
                            Agent.description.ilike(keyword),
                        ),
                    )
                )
                .order_by(func.similarity(Agent.name, query).desc())
                .limit(limit)
            )
            result = await db.execute(stmt)
            return [
                {
                    "id": str(row.id),
                    "name": row.name,
                    "description": row.description,
                    "type": "agent",
                    "score": float(row.sim) if row.sim is not None else 0.0,
                }
                for row in result.all()
            ]
        except Exception:
            await db.rollback()
            result = await db.execute(
                select(Agent.id, Agent.name, Agent.description)
                .where(
                    and_(
                        ownership,
                        or_(
                            Agent.name.ilike(keyword),
                            Agent.description.ilike(keyword),
                        ),
                    )
                )
                .limit(limit * 3)
            )
            items = [
                {
                    "id": str(row.id),
                    "name": row.name,
                    "description": row.description,
                    "type": "agent",
                    "score": compute_search_score(row.name, query),
                }
                for row in result.all()
            ]
            items.sort(key=lambda x: x["score"], reverse=True)
            return items[:limit]

    async def _search_knowledge_bases(self, db, user_id, keyword, query, limit):
        uid = UUID(user_id) if isinstance(user_id, str) else user_id
        try:
            stmt = (
                select(
                    KnowledgeBase.id,
                    KnowledgeBase.name,
                    KnowledgeBase.description,
                    func.similarity(KnowledgeBase.name, query).label("sim"),
                )
                .where(
                    and_(
                        KnowledgeBase.user_id == uid,
                        or_(
                            KnowledgeBase.name.ilike(keyword),
                            KnowledgeBase.description.ilike(keyword),
                        ),
                    )
                )
                .order_by(func.similarity(KnowledgeBase.name, query).desc())
                .limit(limit)
            )
            result = await db.execute(stmt)
            return [
                {
                    "id": str(row.id),
                    "name": row.name,
                    "description": row.description,
                    "type": "knowledge",
                    "score": float(row.sim) if row.sim is not None else 0.0,
                }
                for row in result.all()
            ]
        except Exception:
            await db.rollback()
            result = await db.execute(
                select(
                    KnowledgeBase.id,
                    KnowledgeBase.name,
                    KnowledgeBase.description,
                )
                .where(
                    and_(
                        KnowledgeBase.user_id == uid,
                        or_(
                            KnowledgeBase.name.ilike(keyword),
                            KnowledgeBase.description.ilike(keyword),
                        ),
                    )
                )
                .limit(limit * 3)
            )
            items = [
                {
                    "id": str(row.id),
                    "name": row.name,
                    "description": row.description,
                    "type": "knowledge",
                    "score": compute_search_score(row.name, query),
                }
                for row in result.all()
            ]
            items.sort(key=lambda x: x["score"], reverse=True)
            return items[:limit]

    async def _search_templates(self, db, user_id, keyword, query, limit):
        """Templates: presets + current user's templates."""
        uid = UUID(user_id) if isinstance(user_id, str) else user_id
        ownership = or_(Template.is_preset.is_(True), Template.user_id == uid)
        try:
            stmt = (
                select(
                    Template.id,
                    Template.name,
                    Template.description,
                    func.similarity(Template.name, query).label("sim"),
                )
                .where(
                    and_(
                        ownership,
                        or_(
                            Template.name.ilike(keyword),
                            Template.description.ilike(keyword),
                        ),
                    )
                )
                .order_by(func.similarity(Template.name, query).desc())
                .limit(limit)
            )
            result = await db.execute(stmt)
            return [
                {
                    "id": str(row.id),
                    "name": row.name,
                    "description": row.description,
                    "type": "template",
                    "score": float(row.sim) if row.sim is not None else 0.0,
                }
                for row in result.all()
            ]
        except Exception:
            await db.rollback()
            result = await db.execute(
                select(Template.id, Template.name, Template.description)
                .where(
                    and_(
                        ownership,
                        or_(
                            Template.name.ilike(keyword),
                            Template.description.ilike(keyword),
                        ),
                    )
                )
                .limit(limit * 3)
            )
            items = [
                {
                    "id": str(row.id),
                    "name": row.name,
                    "description": row.description,
                    "type": "template",
                    "score": compute_search_score(row.name, query),
                }
                for row in result.all()
            ]
            items.sort(key=lambda x: x["score"], reverse=True)
            return items[:limit]
