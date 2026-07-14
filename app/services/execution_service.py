import asyncio
import json
import uuid
import structlog
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
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
from app.models.enums import ExecutionSource, ExecutionStatus, NodeStatus
from app.models.execution import Execution, ExecutionNode, Log
from app.models.workflow import Workflow
from app.services.cache_invalidator import CacheInvalidator
from app.schemas.execution import (
    CancelExecutionResponse,
    DailyTrendItem,
    ExecutionDetailResponse,
    ExecutionListItem,
    ExecutionListResponse,
    ExecutionNodeDetail,
    ExecutionStatsResponse,
    ExecutionStatsSummary,
    NodeStats,
    ReviewActionResponse,
    WorkflowStatsItem,
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
            source=ExecutionSource.web.value,
            input_data=input_data,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(execution)
        await self.db.flush()
        await CacheInvalidator.invalidate_dashboard(str(user_id))

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
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> ExecutionListResponse:
        query = (
            select(Execution, Workflow.name)
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(Workflow.user_id == user_id)
        )
        count_query = (
            select(func.count(Execution.id))
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(Workflow.user_id == user_id)
        )

        if workflow_id:
            query = query.where(Execution.workflow_id == workflow_id)
            count_query = count_query.where(Execution.workflow_id == workflow_id)
        if status:
            query = query.where(Execution.status == status)
            count_query = count_query.where(Execution.status == status)
        if start_time:
            query = query.where(Execution.started_at >= start_time)
            count_query = count_query.where(Execution.started_at >= start_time)
        if end_time:
            query = query.where(Execution.started_at <= end_time)
            count_query = count_query.where(Execution.started_at <= end_time)

        total = (await self.db.execute(count_query)).scalar() or 0
        offset = (page - 1) * page_size
        query = (
            query.order_by(Execution.started_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(query)).all()

        items: list[ExecutionListItem] = []
        for execution, workflow_name in rows:
            node_stats_result = await self.db.execute(
                select(
                    func.count(ExecutionNode.id),
                    func.count(ExecutionNode.id).filter(
                        ExecutionNode.status == NodeStatus.success
                    ),
                    func.count(ExecutionNode.id).filter(
                        ExecutionNode.status == NodeStatus.failed
                    ),
                ).where(ExecutionNode.execution_id == execution.id)
            )
            node_total, node_success, node_failed = node_stats_result.one()
            items.append(
                ExecutionListItem(
                    id=execution.id,
                    workflow_id=execution.workflow_id,
                    workflow_name=workflow_name,
                    version_number=execution.version_number,
                    status=execution.status.value,
                    total_duration_ms=execution.total_duration_ms,
                    total_tokens=execution.total_tokens,
                    total_cost=float(execution.total_cost)
                    if execution.total_cost is not None
                    else None,
                    started_at=execution.started_at,
                    finished_at=execution.finished_at,
                    node_count=node_total or 0,
                    success_node_count=node_success or 0,
                    failed_node_count=node_failed or 0,
                )
            )

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

        stats = NodeStats()
        node_details: list[ExecutionNodeDetail] = []
        for n in exec_nodes:
            status_val = n.status.value if hasattr(n.status, "value") else str(n.status)
            stats.total += 1
            if hasattr(stats, status_val):
                setattr(stats, status_val, getattr(stats, status_val) + 1)
            node_details.append(
                ExecutionNodeDetail(
                    id=n.id,
                    execution_id=n.execution_id,
                    node_id=n.node_id,
                    node_type=n.node_type,
                    status=status_val,
                    input_data=n.input_data,
                    output_data=n.output_data,
                    duration_ms=n.duration_ms,
                    tokens_used=n.tokens_used,
                    error_message=n.error_message,
                    started_at=n.started_at,
                    finished_at=n.finished_at,
                )
            )

        success_rate = (
            round(stats.success / stats.total, 2) if stats.total > 0 else 0.0
        )
        log_count = (
            await self.db.execute(
                select(func.count(Log.id)).where(Log.execution_id == execution_id)
            )
        ).scalar() or 0

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
            total_cost=float(execution.total_cost)
            if execution.total_cost is not None
            else None,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
            nodes=node_details,
            node_stats=stats,
            success_rate=success_rate,
            log_count=log_count,
        )

    async def get_execution_nodes(
        self,
        execution_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[ExecutionNodeDetail]:
        detail = await self.get_execution_detail(execution_id, user_id)
        return detail.nodes

    async def get_stats(
        self,
        user_id: uuid.UUID,
        period: str = "7d",
        workflow_id: Optional[uuid.UUID] = None,
    ) -> ExecutionStatsResponse:
        now = datetime.now(timezone.utc)
        period_map = {"7d": 7, "30d": 30, "90d": 90}
        days = period_map.get(period, 7)
        start_time = now - timedelta(days=days)

        base_filter = and_(
            Workflow.user_id == user_id,
            Execution.started_at >= start_time,
        )
        if workflow_id:
            base_filter = and_(base_filter, Execution.workflow_id == workflow_id)

        summary_query = (
            select(
                func.count(Execution.id).label("total"),
                func.count(Execution.id)
                .filter(Execution.status == ExecutionStatus.success)
                .label("success"),
                func.count(Execution.id)
                .filter(Execution.status == ExecutionStatus.failed)
                .label("failed"),
                func.avg(Execution.total_duration_ms)
                .filter(Execution.status == ExecutionStatus.success)
                .label("avg_duration"),
                func.coalesce(func.sum(Execution.total_tokens), 0).label("total_tokens"),
                func.coalesce(func.sum(Execution.total_cost), 0).label("total_cost"),
            )
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(base_filter)
        )
        summary_row = (await self.db.execute(summary_query)).one()

        total = summary_row.total or 0
        success = summary_row.success or 0
        summary = ExecutionStatsSummary(
            total_executions=total,
            success_count=success,
            failed_count=summary_row.failed or 0,
            success_rate=round(success / total, 2) if total > 0 else 0.0,
            avg_duration_ms=round(summary_row.avg_duration or 0),
            total_tokens=int(summary_row.total_tokens or 0),
            total_cost=float(summary_row.total_cost or 0),
        )

        daily_query = (
            select(
                func.date(Execution.started_at).label("date"),
                func.count(Execution.id).label("count"),
                func.count(Execution.id)
                .filter(Execution.status == ExecutionStatus.success)
                .label("success_count"),
                func.avg(Execution.total_duration_ms)
                .filter(Execution.status == ExecutionStatus.success)
                .label("avg_duration"),
            )
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(base_filter)
            .group_by(func.date(Execution.started_at))
            .order_by(func.date(Execution.started_at))
        )
        daily_trend = [
            DailyTrendItem(
                date=str(row.date),
                count=row.count,
                success_count=row.success_count or 0,
                avg_duration_ms=round(row.avg_duration or 0),
            )
            for row in (await self.db.execute(daily_query)).all()
        ]

        by_wf_query = (
            select(
                Workflow.id.label("workflow_id"),
                Workflow.name.label("workflow_name"),
                func.count(Execution.id).label("count"),
                func.count(Execution.id)
                .filter(Execution.status == ExecutionStatus.success)
                .label("success_count"),
                func.avg(Execution.total_duration_ms)
                .filter(Execution.status == ExecutionStatus.success)
                .label("avg_duration"),
            )
            .join(Workflow, Execution.workflow_id == Workflow.id)
            .where(
                and_(Workflow.user_id == user_id, Execution.started_at >= start_time)
            )
            .group_by(Workflow.id, Workflow.name)
            .order_by(func.count(Execution.id).desc())
            .limit(10)
        )
        by_workflow = [
            WorkflowStatsItem(
                workflow_id=str(row.workflow_id),
                workflow_name=row.workflow_name,
                execution_count=row.count,
                success_count=row.success_count or 0,
                avg_duration_ms=round(row.avg_duration or 0),
            )
            for row in (await self.db.execute(by_wf_query)).all()
        ]

        return ExecutionStatsResponse(
            summary=summary,
            daily_trend=daily_trend,
            by_workflow=by_workflow,
        )

