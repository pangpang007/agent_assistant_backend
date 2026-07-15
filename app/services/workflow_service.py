"""工作流 CRUD 服务。"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException, WorkflowNotFoundError
from app.models.workflow import Workflow
from app.schemas.workflow import WorkflowListItem
from app.services.cache_invalidator import CacheInvalidator
from app.services.version_service import VersionService


class WorkflowService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.version_service = VersionService(db)

    async def list_workflows(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> dict:
        query = select(Workflow).where(Workflow.user_id == user_id)
        count_query = select(func.count(Workflow.id)).where(Workflow.user_id == user_id)

        if keyword:
            like_pattern = f"%{keyword}%"
            query = query.where(
                (Workflow.name.ilike(like_pattern))
                | (Workflow.description.ilike(like_pattern))
            )
            count_query = count_query.where(
                (Workflow.name.ilike(like_pattern))
                | (Workflow.description.ilike(like_pattern))
            )

        sort_column = getattr(Workflow, sort_by, Workflow.updated_at)
        query = query.order_by(
            sort_column.desc() if sort_order == "desc" else sort_column.asc()
        )

        total = (await self.db.execute(count_query)).scalar() or 0
        offset = (page - 1) * page_size
        workflows = (
            await self.db.execute(query.offset(offset).limit(page_size))
        ).scalars().all()

        items = [
            WorkflowListItem(
                id=wf.id,
                name=wf.name,
                description=wf.description,
                node_count=len(wf.nodes_data) if wf.nodes_data else 0,
                current_version=wf.current_version,
                is_published_api=wf.is_published_api,
                created_at=wf.created_at,
                updated_at=wf.updated_at,
            )
            for wf in workflows
        ]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": offset + page_size < total,
        }

    async def create_workflow(
        self,
        user_id: UUID,
        name: str,
        description: Optional[str] = None,
        nodes_data: Optional[list] = None,
        edges_data: Optional[list] = None,
    ) -> Workflow:
        workflow = Workflow(
            user_id=user_id,
            name=name,
            description=description,
            nodes_data=nodes_data or [],
            edges_data=edges_data or [],
            current_version=1,
        )
        self.db.add(workflow)
        await self.db.flush()

        await self.version_service.create_version(
            workflow_id=workflow.id,
            version_number=1,
            nodes_data=workflow.nodes_data,
            edges_data=workflow.edges_data,
            tag="初始版本",
        )
        await self.db.flush()
        await CacheInvalidator.invalidate_dashboard(str(user_id))
        await CacheInvalidator.invalidate_search(str(user_id))
        return workflow

    async def get_workflow(self, workflow_id: UUID, user_id: UUID) -> Workflow:
        workflow = (
            await self.db.execute(select(Workflow).where(Workflow.id == workflow_id))
        ).scalar_one_or_none()
        if not workflow:
            raise WorkflowNotFoundError()
        if workflow.user_id != user_id:
            raise ForbiddenException("无权操作此工作流")
        return workflow

    async def update_workflow(
        self,
        workflow: Workflow,
        name: Optional[str] = None,
        description: Optional[str] = None,
        nodes_data: Optional[list] = None,
        edges_data: Optional[list] = None,
    ) -> Workflow:
        has_data_change = False

        if name is not None:
            workflow.name = name
        if description is not None:
            workflow.description = description
        if nodes_data is not None:
            if nodes_data != workflow.nodes_data:
                has_data_change = True
            workflow.nodes_data = nodes_data
        if edges_data is not None:
            if edges_data != workflow.edges_data:
                has_data_change = True
            workflow.edges_data = edges_data

        if has_data_change:
            new_version = workflow.current_version + 1
            workflow.current_version = new_version
            await self.version_service.create_version(
                workflow_id=workflow.id,
                version_number=new_version,
                nodes_data=workflow.nodes_data,
                edges_data=workflow.edges_data,
            )

        workflow.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(workflow)
        return workflow

    async def delete_workflow(self, workflow_id: UUID, user_id: UUID) -> None:
        workflow = await self.get_workflow(workflow_id, user_id)
        if workflow.published_api_key:
            await CacheInvalidator.invalidate_api_key(workflow.published_api_key)
        await self.db.delete(workflow)
        await self.db.flush()
        await CacheInvalidator.invalidate_dashboard(str(user_id))
        await CacheInvalidator.invalidate_search(str(user_id))

    async def export_workflow(self, workflow: Workflow) -> dict:
        return {
            "id": str(workflow.id),
            "name": workflow.name,
            "description": workflow.description,
            "version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "nodes_data": workflow.nodes_data or [],
            "edges_data": workflow.edges_data or [],
            "metadata": {
                "current_version": workflow.current_version,
                "node_count": len(workflow.nodes_data) if workflow.nodes_data else 0,
                "edge_count": len(workflow.edges_data) if workflow.edges_data else 0,
            },
        }

    async def import_workflow(
        self,
        user_id: UUID,
        import_data: dict,
        name_override: Optional[str] = None,
    ) -> Workflow:
        name = name_override or import_data.get("name", "未命名工作流")

        existing = (
            await self.db.execute(
                select(Workflow).where(
                    Workflow.user_id == user_id, Workflow.name == name
                )
            )
        ).scalar_one_or_none()
        if existing:
            suffix = 1
            while True:
                check_name = f"{name}({suffix})"
                dup = (
                    await self.db.execute(
                        select(Workflow).where(
                            Workflow.user_id == user_id, Workflow.name == check_name
                        )
                    )
                ).scalar_one_or_none()
                if not dup:
                    name = check_name
                    break
                suffix += 1

        return await self.create_workflow(
            user_id=user_id,
            name=name,
            description=import_data.get("description"),
            nodes_data=import_data.get("nodes_data", []),
            edges_data=import_data.get("edges_data", []),
        )
