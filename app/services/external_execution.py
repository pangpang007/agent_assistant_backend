"""Synchronous external API workflow execution."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import MissingInputError
from app.core.redis import get_redis
from app.models.enums import ExecutionSource, ExecutionStatus
from app.models.execution import Execution
from app.models.workflow import Workflow
from app.services.execution.executor import WorkflowExecutor

logger = structlog.get_logger()


class ExternalExecutionService:
    """外部 API 触发工作流执行（同步等待结果）。"""

    async def run_workflow(
        self,
        db: AsyncSession,
        workflow: Workflow,
        input_data: dict[str, Any],
    ) -> dict:
        start_time = time.time()
        timeout = settings.external_api_timeout_seconds

        self._validate_input(workflow, input_data)

        execution = Execution(
            id=uuid.uuid4(),
            workflow_id=workflow.id,
            version_number=workflow.current_version,
            status=ExecutionStatus.pending,
            source=ExecutionSource.api.value,
            api_caller_workflow_id=workflow.id,
            input_data=input_data,
            started_at=datetime.now(timezone.utc),
        )
        db.add(execution)
        await db.flush()

        try:
            redis = get_redis()
            executor = WorkflowExecutor(db=db, redis=redis)

            await asyncio.wait_for(
                executor.execute(
                    execution=execution,
                    nodes_data=workflow.nodes_data or [],
                    edges_data=workflow.edges_data or [],
                    input_data=input_data,
                    user_id=workflow.user_id,
                    resume_state=None,
                ),
                timeout=timeout,
            )

            # Executor already updates status/output on the ORM object
            await db.refresh(execution)
            duration_ms = execution.total_duration_ms or int(
                (time.time() - start_time) * 1000
            )
            status_val = (
                execution.status.value
                if hasattr(execution.status, "value")
                else str(execution.status)
            )
            success = status_val == ExecutionStatus.success.value

            await self._bump_api_stats(
                db, workflow.id, duration_ms, success=success
            )
            await db.flush()

            error_msg = None
            if not success:
                error_msg = (
                    "工作流执行失败"
                    if status_val == ExecutionStatus.failed.value
                    else f"执行状态: {status_val}"
                )

            return {
                "execution_id": str(execution.id),
                "status": "success" if success else "failed",
                "output": execution.output_data if success else None,
                "duration_ms": duration_ms,
                "error": error_msg,
            }

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            execution.status = ExecutionStatus.failed
            execution.total_duration_ms = duration_ms
            execution.finished_at = datetime.now(timezone.utc)
            await self._bump_api_stats(
                db, workflow.id, duration_ms, success=False
            )
            await db.flush()
            return {
                "execution_id": str(execution.id),
                "status": "failed",
                "output": None,
                "duration_ms": duration_ms,
                "error": f"工作流执行超时（超过 {timeout} 秒）",
            }

        except Exception as exc:
            logger.error("external_execution_error", error=str(exc))
            duration_ms = int((time.time() - start_time) * 1000)
            execution.status = ExecutionStatus.failed
            execution.total_duration_ms = duration_ms
            execution.finished_at = datetime.now(timezone.utc)
            await self._bump_api_stats(
                db, workflow.id, duration_ms, success=False
            )
            await db.flush()
            return {
                "execution_id": str(execution.id),
                "status": "failed",
                "output": None,
                "duration_ms": duration_ms,
                "error": str(exc),
            }

    async def _bump_api_stats(
        self,
        db: AsyncSession,
        workflow_id: uuid.UUID,
        duration_ms: int,
        *,
        success: bool,
    ) -> None:
        values = {
            "api_call_count": Workflow.api_call_count + 1,
            "api_total_duration_ms": Workflow.api_total_duration_ms + duration_ms,
        }
        if success:
            values["api_success_count"] = Workflow.api_success_count + 1
        await db.execute(
            update(Workflow).where(Workflow.id == workflow_id).values(**values)
        )

    def _validate_input(self, workflow: Workflow, input_data: dict) -> None:
        if not workflow.nodes_data:
            return

        start_nodes = [
            n for n in workflow.nodes_data if n.get("type") == "startNode"
        ]
        if not start_nodes:
            return

        start_node = start_nodes[0]
        defined_inputs = start_node.get("data", {}).get("inputs", []) or []

        for inp in defined_inputs:
            name = inp.get("name")
            if not name:
                continue
            if inp.get("required", False) and name not in input_data:
                raise MissingInputError(name)
