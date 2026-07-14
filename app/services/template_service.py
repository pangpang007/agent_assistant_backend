import copy
import uuid
from typing import Optional

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ForbiddenException,
    PresetTemplateProtectedError,
    TemplateNotFoundError,
    WorkflowNotFoundError,
)
from app.models.template import Template
from app.models.workflow import Workflow
from app.schemas.template import TemplateListItem, TemplateListResponse

logger = structlog.get_logger()


class TemplateService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_templates(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        is_preset: Optional[bool] = None,
        sort_by: str = "use_count",
        sort_order: str = "desc",
    ) -> TemplateListResponse:
        query = select(Template)
        count_query = select(func.count(Template.id))

        if keyword:
            like_pattern = f"%{keyword}%"
            condition = or_(
                Template.name.ilike(like_pattern),
                Template.description.ilike(like_pattern),
            )
            query = query.where(condition)
            count_query = count_query.where(condition)

        if category:
            query = query.where(Template.category == category)
            count_query = count_query.where(Template.category == category)

        if is_preset is not None:
            query = query.where(Template.is_preset == is_preset)
            count_query = count_query.where(Template.is_preset == is_preset)

        sort_column = getattr(Template, sort_by, Template.use_count)
        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        total = (await self.db.execute(count_query)).scalar() or 0
        offset = (page - 1) * page_size
        result = await self.db.execute(query.offset(offset).limit(page_size))
        templates = result.scalars().all()

        items = [
            TemplateListItem(
                id=tpl.id,
                name=tpl.name,
                description=tpl.description,
                category=tpl.category,
                thumbnail_url=tpl.thumbnail_url,
                use_count=tpl.use_count,
                node_count=len(tpl.nodes_data) if tpl.nodes_data else 0,
                is_preset=tpl.is_preset,
                created_at=tpl.created_at,
            )
            for tpl in templates
        ]

        return TemplateListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=offset + page_size < total,
        )

    async def get_template(self, template_id: uuid.UUID) -> Template:
        result = await self.db.execute(
            select(Template).where(Template.id == template_id)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise TemplateNotFoundError()
        return template

    async def save_as_template(
        self,
        workflow_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        description: Optional[str] = None,
        category: str = "自定义",
        thumbnail_url: Optional[str] = None,
    ) -> Template:
        result = await self.db.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise WorkflowNotFoundError()
        if workflow.user_id != user_id:
            raise ForbiddenException("无权将此工作流保存为模板")

        template = Template(
            user_id=user_id,
            workflow_id=workflow.id,
            name=name,
            description=description,
            category=category,
            thumbnail_url=thumbnail_url,
            nodes_data=copy.deepcopy(workflow.nodes_data) if workflow.nodes_data else [],
            edges_data=copy.deepcopy(workflow.edges_data) if workflow.edges_data else [],
            is_preset=False,
            use_count=0,
        )
        self.db.add(template)
        await self.db.flush()
        logger.info(
            "template_saved",
            template_id=str(template.id),
            workflow_id=str(workflow_id),
        )
        return template

    async def use_template(
        self,
        template_id: uuid.UUID,
        user_id: uuid.UUID,
        name_override: Optional[str] = None,
    ) -> Workflow:
        template = await self.get_template(template_id)
        name = name_override or f"{template.name} - 副本"

        from app.services.workflow_service import WorkflowService

        workflow_service = WorkflowService(self.db)
        workflow = await workflow_service.create_workflow(
            user_id=user_id,
            name=name,
            description=f"从模板「{template.name}」创建",
            nodes_data=copy.deepcopy(template.nodes_data) if template.nodes_data else [],
            edges_data=copy.deepcopy(template.edges_data) if template.edges_data else [],
        )

        template.use_count += 1
        await self.db.flush()
        logger.info(
            "template_used",
            template_id=str(template_id),
            workflow_id=str(workflow.id),
        )
        return workflow

    async def delete_template(
        self, template_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        template = await self.get_template(template_id)

        if template.is_preset:
            raise PresetTemplateProtectedError()
        if template.user_id != user_id:
            raise ForbiddenException("无权删除此模板")

        await self.db.delete(template)
        await self.db.flush()
