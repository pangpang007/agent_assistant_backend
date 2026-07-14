import asyncio
import json
import uuid
import structlog
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.exceptions import (
    ExecutionNotCancellableError,
    ExecutionNotFoundError,
    ExecutionNotPausedError,
    ForbiddenException,
    InvalidReviewNodeError,
    WorkflowEmptyError,
    WorkflowNotFoundError,
)
from app.models.enums import ExecutionStatus, NodeStatus
from app.models.execution import Execution, ExecutionNode
from app.models.workflow import Workflow
from app.schemas.execution import (
    CancelExecutionResponse,
    ExecutionDetailResponse,
    ExecutionListItem,
    ExecutionListResponse,
    ExecutionNodeDetail,
    ReviewActionResponse,
)
from app.services.execution.cancellation import CancellationManager
from app.services.execution.executor import CHECKPOINT_KEY_PREFIX, WorkflowExecutor
from app.services.execution.review_manager import ReviewManager
from app.services.execution.ws_broadcaster import ws_manager

logger = structlog.get_logger()


class ExecutionService:
    """执行管理服务。"""

    def __init__(self, db: AsyncSession, redis):
        self.db = db
        self.redis = redis

    async def start_execution(
        self,
        workflow_id: uuid.UUID,
        user_id: uuid.UUID,
        input_data: dict,
    ) -> Execution:
        workflow = await self.db.get(Workflow, workflow_id)
        if not workflow:
            raise WorkflowNotFoundError()
        if workflow.user_id != user_id:
            raise ForbiddenException("无权执行此工作流")

        if not workflow.nodes_data or not workflow.edges_data:
            raise WorkflowEmptyError()

        execution = Execution(
            id=uuid.uuid4(),
            workflow_id=workflow_id,
            version_number=workflow.current_version,
            status=ExecutionStatus.pending,
            input_data=input_data,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(execution)
        await self.db.flush()

        execution_id = execution.id
        nodes_data = workflow.nodes_data
        edges_data = workflow.edges_data

        asyncio.create_task(
            self._run_execution_background(
                execution_id=execution_id,
                workflow_id=workflow_id,
                nodes_data=nodes_data,
                edges_data=edges_data,
                input_data=input_data,
                user_id=user_id,
            )
        )

        return execution

    async def _run_execution_background(
        self,
        execution_id: uuid.UUID,
        workflow_id: uuid.UUID,
        nodes_data: list,
        edges_data: list,
        input_data: dict,
        user_id: uuid.UUID,
        resume_state: Optional[dict[str, Any]] = None,
    ) -> None:
        async with async_session_factory() as session:
            try:
                execution = await session.get(Execution, execution_id)
                if not execution:
                    logger.error("execution_not_found_background", execution_id=str(execution_id))
                    return

                executor = WorkflowExecutor(
                    db=session,
                    redis=self.redis,
                    broadcaster=ws_manager,
                    cancellation_mgr=CancellationManager(self.redis),
                    review_mgr=ReviewManager(self.redis),
                )
                await executor.execute(
                    execution=execution,
                    nodes_data=nodes_data,
                    edges_data=edges_data,
                    input_data=input_data,
                    user_id=user_id,
                    resume_state=resume_state,
                )
            except Exception as exc:
                logger.error("execution_background_error", error=str(exc))
            finally:
                await session.commit()

    async def cancel_execution(
        self,
        execution_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> CancelExecutionResponse:
        execution = await self.db.get(Execution, execution_id)
        if not execution:
            raise ExecutionNotFoundError()

        workflow = await self.db.get(Workflow, execution.workflow_id)
        if not workflow or workflow.user_id != user_id:
            raise ForbiddenException("无权操作此执行记录")

        if execution.status not in (
            ExecutionStatus.running,
            ExecutionStatus.paused,
            ExecutionStatus.pending,
        ):
            raise ExecutionNotCancellableError(execution.status.value)

        cancellation_mgr = CancellationManager(self.redis)
        await cancellation_mgr.set_cancelled(execution_id)

        if execution.status == ExecutionStatus.paused:
            await self.redis.publish(f"resume:{execution_id}", "{}")

        return CancelExecutionResponse(execution_id=execution_id)

    async def submit_review(
        self,
        execution_id: uuid.UUID,
        node_id: str,
        user_id: uuid.UUID,
        action: str,
        comment: Optional[str] = None,
        modified_data: Optional[dict] = None,
    ) -> ReviewActionResponse:
        execution = await self.db.get(Execution, execution_id)
        if not execution:
            raise ExecutionNotFoundError()

        workflow = await self.db.get(Workflow, execution.workflow_id)
        if not workflow or workflow.user_id != user_id:
            raise ForbiddenException("无权操作此执行记录")

        if execution.status != ExecutionStatus.paused:
            raise ExecutionNotPausedError()

        result = await self.db.execute(
            select(ExecutionNode).where(
                ExecutionNode.execution_id == execution_id,
                ExecutionNode.node_id == node_id,
            )
        )
        exec_node = result.scalar_one_or_none()
        if not exec_node or exec_node.node_type != "reviewNode":
            raise InvalidReviewNodeError()

        review_output = WorkflowExecutor.build_review_output(
            action, comment, modified_data
        )

        if action == "reject":
            exec_node.status = NodeStatus.failed
            exec_node.error_message = f"审核被拒绝: {comment or '无备注'}"
        else:
            exec_node.status = NodeStatus.success

        exec_node.output_data = review_output
        exec_node.finished_at = datetime.now(timezone.utc)
        execution.status = ExecutionStatus.running
        await self.db.flush()

        review_mgr = ReviewManager(self.redis)
        await review_mgr.submit_review(
            execution_id=execution_id,
            node_id=node_id,
            action=action,
            comment=comment,
            modified_data=modified_data,
        )

        await ws_manager.broadcast(
            execution_id,
            {
                "type": "review_result",
                "node_id": node_id,
                "action": action,
                "comment": comment,
                "modified_data": modified_data,
            },
        )

        checkpoint_raw = await self.redis.get(f"{CHECKPOINT_KEY_PREFIX}{execution_id}")
        if not checkpoint_raw:
            raise ExecutionNotFoundError()

        checkpoint = json.loads(checkpoint_raw)
        resume_state = {
            "start_index": checkpoint.get("start_index", 0),
            "context_state": checkpoint.get("context_state", {}),
            "skip_set": checkpoint.get("skip_set", []),
            "start_time": checkpoint.get("start_time"),
            "total_tokens": checkpoint.get("total_tokens", 0),
            "review_node_id": node_id,
            "review_output": review_output,
        }

        if action == "reject":
            execution.status = ExecutionStatus.failed
            execution.finished_at = datetime.now(timezone.utc)
            await self.db.flush()
            await ws_manager.broadcast(
                execution_id,
                {
                    "type": "execution_status",
                    "status": "failed",
                    "error": exec_node.error_message,
                },
            )
            await self.redis.delete(f"{CHECKPOINT_KEY_PREFIX}{execution_id}")
            return ReviewActionResponse(
                execution_id=execution_id,
                node_id=node_id,
                action=action,
                message="审核已拒绝，执行已终止",
            )

        await self.redis.delete(f"{CHECKPOINT_KEY_PREFIX}{execution_id}")

        asyncio.create_task(
            self._run_execution_background(
                execution_id=execution_id,
                workflow_id=execution.workflow_id,
                nodes_data=checkpoint.get("nodes_data", workflow.nodes_data or []),
                edges_data=checkpoint.get("edges_data", workflow.edges_data or []),
                input_data=checkpoint.get("input_data", execution.input_data or {}),
                user_id=user_id,
                resume_state=resume_state,
            )
        )

        return ReviewActionResponse(
            execution_id=execution_id,
            node_id=node_id,
            action=action,
        )

    async def list_executions(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        workflow_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
    ) -> ExecutionListResponse:
        query = (
            select(Execution, Workflow.name)
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(Workflow.user_id == user_id)
        )

        if workflow_id:
            query = query.where(Execution.workflow_id == workflow_id)
        if status:
            query = query.where(Execution.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        offset = (page - 1) * page_size
        query = (
            query.order_by(Execution.started_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(query)).all()

        items = [
            ExecutionListItem(
                id=execution.id,
                workflow_id=execution.workflow_id,
                workflow_name=workflow_name,
                version_number=execution.version_number,
                status=execution.status.value,
                total_duration_ms=execution.total_duration_ms,
                total_tokens=execution.total_tokens,
                started_at=execution.started_at,
                finished_at=execution.finished_at,
            )
            for execution, workflow_name in rows
        ]

        return ExecutionListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=(offset + page_size) < total,
        )

    async def get_execution_detail(
        self,
        execution_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ExecutionDetailResponse:
        execution = await self.db.get(Execution, execution_id)
        if not execution:
            raise ExecutionNotFoundError()

        workflow = await self.db.get(Workflow, execution.workflow_id)
        if not workflow or workflow.user_id != user_id:
            raise ForbiddenException("无权查看此执行记录")

        nodes_result = await self.db.execute(
            select(ExecutionNode)
            .where(ExecutionNode.execution_id == execution_id)
            .order_by(ExecutionNode.started_at)
        )
        exec_nodes = nodes_result.scalars().all()

        node_details = [
            ExecutionNodeDetail(
                id=n.id,
                execution_id=n.execution_id,
                node_id=n.node_id,
                node_type=n.node_type,
                status=n.status.value,
                input_data=n.input_data,
                output_data=n.output_data,
                duration_ms=n.duration_ms,
                tokens_used=n.tokens_used,
                error_message=n.error_message,
                started_at=n.started_at,
                finished_at=n.finished_at,
            )
            for n in exec_nodes
        ]

        return ExecutionDetailResponse(
            id=execution.id,
            workflow_id=execution.workflow_id,
            workflow_name=workflow.name,
            version_number=execution.version_number,
            status=execution.status.value,
            input_data=execution.input_data,
            output_data=execution.output_data,
            total_duration_ms=execution.total_duration_ms,
            total_tokens=execution.total_tokens,
            total_cost=execution.total_cost,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
            nodes=node_details,
        )

    async def get_execution_nodes(
        self,
        execution_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[ExecutionNodeDetail]:
        detail = await self.get_execution_detail(execution_id, user_id)
        return detail.nodes
