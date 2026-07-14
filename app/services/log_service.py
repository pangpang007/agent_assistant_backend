import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ExecutionNotFoundError,
    ForbiddenException,
    LogNotFoundError,
)
from app.models.execution import Execution, Log
from app.models.workflow import Workflow
from app.schemas.execution import (
    LogDetailResponse,
    LogListParams,
    LogListResponse,
)
from app.schemas.log import (
    LogDetailResponse as GlobalLogDetailResponse,
)
from app.schemas.log import LogListItem, LogListResponse as GlobalLogListResponse


class LogService:
    """日志服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _verify_execution_access(
        self, execution_id: uuid.UUID, user_id: uuid.UUID
    ) -> Execution:
        execution = await self.db.get(Execution, execution_id)
        if not execution:
            raise ExecutionNotFoundError()

        workflow = await self.db.get(Workflow, execution.workflow_id)
        if not workflow or workflow.user_id != user_id:
            raise ForbiddenException("无权查看此执行日志")

        return execution

    async def list_logs(
        self,
        user_id: uuid.UUID,
        params: LogListParams,
        execution_id: Optional[uuid.UUID] = None,
    ) -> LogListResponse:
        """按执行记录查询日志（Phase 5 `/api/executions/{id}/logs`）。"""
        query = select(Log)

        target_execution_id = execution_id or params.execution_id
        if target_execution_id:
            await self._verify_execution_access(target_execution_id, user_id)
            query = query.where(Log.execution_id == target_execution_id)

        if params.node_id:
            query = query.where(Log.node_id == params.node_id)
        if params.level:
            query = query.where(Log.level == params.level)

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        offset = (params.page - 1) * params.page_size
        query = (
            query.order_by(Log.timestamp.desc())
            .offset(offset)
            .limit(params.page_size)
        )
        logs = (await self.db.execute(query)).scalars().all()

        items = [
            LogDetailResponse(
                id=log.id,
                execution_id=log.execution_id,
                node_id=log.node_id,
                level=log.level.value,
                message=log.message,
                timestamp=log.timestamp,
            )
            for log in logs
        ]

        return LogListResponse(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            has_next=(offset + params.page_size) < total,
        )

    async def list_global_logs(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
        level: Optional[str] = None,
        execution_id: Optional[uuid.UUID] = None,
        node_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        search: Optional[str] = None,
    ) -> GlobalLogListResponse:
        """全局日志中心列表。"""
        query = (
            select(Log, Workflow.name.label("workflow_name"))
            .join(Execution, Log.execution_id == Execution.id)
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(Workflow.user_id == user_id)
        )
        count_query = (
            select(func.count(Log.id))
            .join(Execution, Log.execution_id == Execution.id)
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(Workflow.user_id == user_id)
        )

        if level:
            query = query.where(Log.level == level)
            count_query = count_query.where(Log.level == level)
        if execution_id:
            query = query.where(Log.execution_id == execution_id)
            count_query = count_query.where(Log.execution_id == execution_id)
        if node_id:
            query = query.where(Log.node_id == node_id)
            count_query = count_query.where(Log.node_id == node_id)
        if start_time:
            query = query.where(Log.timestamp >= start_time)
            count_query = count_query.where(Log.timestamp >= start_time)
        if end_time:
            query = query.where(Log.timestamp <= end_time)
            count_query = count_query.where(Log.timestamp <= end_time)
        if search:
            like_pattern = f"%{search}%"
            query = query.where(Log.message.ilike(like_pattern))
            count_query = count_query.where(Log.message.ilike(like_pattern))

        query = query.order_by(Log.timestamp.desc())
        total = (await self.db.execute(count_query)).scalar() or 0
        offset = (page - 1) * page_size
        rows = (await self.db.execute(query.offset(offset).limit(page_size))).all()

        items = [
            LogListItem(
                id=log.id,
                execution_id=log.execution_id,
                workflow_name=workflow_name,
                level=log.level.value if hasattr(log.level, "value") else str(log.level),
                message=log.message,
                node_id=log.node_id,
                timestamp=log.timestamp,
            )
            for log, workflow_name in rows
        ]

        return GlobalLogListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=offset + page_size < total,
        )

    async def get_log_detail(
        self,
        log_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> GlobalLogDetailResponse:
        result = await self.db.execute(
            select(
                Log,
                Workflow.name.label("workflow_name"),
                Workflow.id.label("workflow_id"),
                Workflow.user_id.label("owner_id"),
            )
            .join(Execution, Log.execution_id == Execution.id)
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(Log.id == log_id)
        )
        row = result.one_or_none()
        if not row:
            raise LogNotFoundError()

        log, workflow_name, workflow_id, owner_id = row
        if owner_id != user_id:
            raise ForbiddenException("无权查看此日志")

        return GlobalLogDetailResponse(
            id=log.id,
            execution_id=log.execution_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            level=log.level.value if hasattr(log.level, "value") else str(log.level),
            message=log.message,
            node_id=log.node_id,
            timestamp=log.timestamp,
            metadata={},
        )
