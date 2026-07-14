import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ExecutionNotFoundError, ForbiddenException, NotFoundException
from app.models.execution import Execution, Log
from app.models.workflow import Workflow
from app.schemas.execution import LogDetailResponse, LogListParams, LogListResponse


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

    async def get_log_detail(
        self,
        log_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> LogDetailResponse:
        log = await self.db.get(Log, log_id)
        if not log:
            raise NotFoundException("日志", str(log_id))

        await self._verify_execution_access(log.execution_id, user_id)

        return LogDetailResponse(
            id=log.id,
            execution_id=log.execution_id,
            node_id=log.node_id,
            level=log.level.value,
            message=log.message,
            timestamp=log.timestamp,
        )
