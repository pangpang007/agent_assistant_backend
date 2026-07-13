"""单节点调试服务。"""

import structlog
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ForbiddenException,
    UnsupportedNodeTypeError,
    WorkflowNotFoundError,
)
from app.models.workflow import Workflow
from app.services.workflow_executors.base import ExecutionContext, NodeExecutionResult
from app.services.workflow_executors.registry import NodeExecutorRegistry

logger = structlog.get_logger()


class NodeTestService:
    def __init__(self, db: AsyncSession, redis=None):
        self.db = db
        self.redis = redis

    async def test_node(
        self,
        workflow_id: UUID,
        user_id: UUID,
        node_id: str,
        node_type: str,
        config: dict,
        input_variables: dict,
    ) -> NodeExecutionResult:
        workflow = (
            await self.db.execute(select(Workflow).where(Workflow.id == workflow_id))
        ).scalar_one_or_none()
        if not workflow:
            raise WorkflowNotFoundError()
        if workflow.user_id != user_id:
            raise ForbiddenException("无权调试此工作流")

        try:
            executor = NodeExecutorRegistry.get_executor(node_type)
        except ValueError as e:
            raise UnsupportedNodeTypeError(node_type) from e

        context = ExecutionContext(
            workflow_id=str(workflow_id),
            user_id=str(user_id),
            db_session=self.db,
            redis_client=self.redis,
        )

        result = await executor.execute(config, input_variables, context)
        logger.info(
            "node_test_completed",
            workflow_id=str(workflow_id),
            node_id=node_id,
            node_type=node_type,
            duration_ms=result.duration_ms,
        )
        return result
