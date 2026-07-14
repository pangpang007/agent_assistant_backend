import asyncio
import json
import time
import uuid
import structlog
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import Execution, ExecutionNode, Log
from app.models.enums import ExecutionStatus, LogLevel, NodeStatus
from app.services.execution.context import ExecutionContext
from app.services.execution.topo_sorter import TopoSorter
from app.services.execution.variable_resolver import VariableResolver
from app.services.execution.ws_broadcaster import WSBroadcaster
from app.services.execution.cancellation import CancellationManager
from app.services.execution.review_manager import ReviewManager
from app.services.workflow_executors.registry import NodeExecutorRegistry

logger = structlog.get_logger()

CHECKPOINT_KEY_PREFIX = "execution_checkpoint:"


class ReviewPausedException(Exception):
    """审核暂停异常，用于中断工作流执行。"""

    def __init__(self, node_id: str):
        self.node_id = node_id
        super().__init__(f"Execution paused at review node {node_id}")


class ExecutionNodeError(Exception):
    """节点执行错误。"""

    def __init__(self, message: str, node_id: str | None = None):
        super().__init__(message)
        self.node_id = node_id


class WorkflowExecutor:
    """工作流执行引擎主类。"""

    def __init__(
        self,
        db: AsyncSession,
        redis,
        broadcaster: WSBroadcaster | None = None,
        cancellation_mgr: CancellationManager | None = None,
        review_mgr: ReviewManager | None = None,
    ):
        self.db = db
        self.redis = redis
        self.broadcaster = broadcaster or WSBroadcaster()
        self.cancellation_mgr = cancellation_mgr or CancellationManager(redis)
        self.review_mgr = review_mgr or ReviewManager(redis)

    async def execute(
        self,
        execution: Execution,
        nodes_data: list[dict],
        edges_data: list[dict],
        input_data: dict[str, Any],
        user_id: uuid.UUID,
        resume_state: Optional[dict[str, Any]] = None,
    ) -> None:
        start_time = resume_state.get("start_time", time.time()) if resume_state else time.time()
        total_tokens = resume_state.get("total_tokens", 0) if resume_state else 0
        start_index = resume_state.get("start_index", 0) if resume_state else 0

        ctx = ExecutionContext(
            execution_id=execution.id,
            workflow_id=execution.workflow_id,
            user_id=user_id,
            db_session=self.db,
            redis_client=self.redis,
            broadcaster=self.broadcaster,
            cancellation_mgr=self.cancellation_mgr,
            review_mgr=self.review_mgr,
        )
        ctx.set_graph(nodes_data, edges_data)

        if resume_state:
            state = resume_state.get("context_state", {})
            ctx.restore_state(
                state.get("global_input", input_data),
                state.get("node_outputs", {}),
            )
            review_output = resume_state.get("review_output")
            review_node_id = resume_state.get("review_node_id")
            if review_output and review_node_id:
                ctx.set_node_output(review_node_id, review_output)
        else:
            ctx.set_global_input(input_data)

        sorter = TopoSorter(nodes_data, edges_data)
        execution_order = sorter.sort()

        if resume_state and resume_state.get("skip_set"):
            sorter.restore_skip_set(set(resume_state["skip_set"]))

        execution.status = ExecutionStatus.running
        await self.db.flush()

        await self.broadcaster.broadcast(
            execution.id,
            {
                "type": "execution_status",
                "status": "running",
                "total_nodes": len(execution_order),
            },
        )

        try:
            for step_index in range(start_index, len(execution_order)):
                step = execution_order[step_index]
                node = step["node"]
                node_id = node["id"]
                node_type = node["type"]

                if await self.cancellation_mgr.is_cancelled(execution.id):
                    await self._handle_cancellation(execution, start_time, total_tokens)
                    return

                group = step.get("group")
                if group and (
                    group.startswith("parallel_") or group.startswith("loop_")
                ):
                    continue

                if step.get("skip", False) or sorter.should_skip(node_id):
                    step["skip"] = True
                    await self._skip_node(execution, node_id, node_type)
                    continue

                if node_type == "reviewNode":
                    await self._pause_for_review(
                        execution=execution,
                        node=node,
                        ctx=ctx,
                        step_index=step_index,
                        execution_order=execution_order,
                        sorter=sorter,
                        nodes_data=nodes_data,
                        edges_data=edges_data,
                        input_data=input_data,
                        user_id=user_id,
                        start_time=start_time,
                        total_tokens=total_tokens,
                    )
                    return

                result = await self._execute_node(execution=execution, node=node, ctx=ctx)

                if result.get("tokens_used"):
                    total_tokens += result["tokens_used"]

                if node_type == "conditionNode":
                    matched_branch = result.get("output", {}).get("matched_branch")
                    sorter.mark_branch_result(node_id, matched_branch, edges_data)
                    for future_step in execution_order:
                        if sorter.should_skip(future_step["node"]["id"]):
                            future_step["skip"] = True

                if result.get("error") and node.get("data", {}).get("on_failure", "abort") == "abort":
                    raise ExecutionNodeError(result["error"], node_id=node_id)

            execution.status = ExecutionStatus.success
            execution.output_data = ctx.get_end_outputs()
            execution.total_duration_ms = int((time.time() - start_time) * 1000)
            execution.total_tokens = total_tokens
            execution.finished_at = datetime.now(timezone.utc)

            await self.broadcaster.broadcast(
                execution.id,
                {
                    "type": "execution_status",
                    "status": "success",
                    "total_duration_ms": execution.total_duration_ms,
                    "total_tokens": total_tokens,
                    "output": execution.output_data,
                },
            )

        except ReviewPausedException as exc:
            execution.status = ExecutionStatus.paused
            await self.db.flush()
            await self.broadcaster.broadcast(
                execution.id,
                {
                    "type": "execution_paused",
                    "execution_id": str(execution.id),
                    "node_id": exc.node_id,
                    "reason": "review",
                },
            )

        except ExecutionNodeError as exc:
            execution.status = ExecutionStatus.failed
            execution.total_duration_ms = int((time.time() - start_time) * 1000)
            execution.total_tokens = total_tokens
            execution.finished_at = datetime.now(timezone.utc)
            await self._log_error(execution.id, exc.node_id, str(exc))
            await self.broadcaster.broadcast(
                execution.id,
                {
                    "type": "execution_status",
                    "status": "failed",
                    "total_duration_ms": execution.total_duration_ms,
                    "error": str(exc),
                },
            )
            logger.error(
                "execution_failed",
                execution_id=str(execution.id),
                error=str(exc),
            )

        except Exception as exc:
            execution.status = ExecutionStatus.failed
            execution.total_duration_ms = int((time.time() - start_time) * 1000)
            execution.total_tokens = total_tokens
            execution.finished_at = datetime.now(timezone.utc)
            await self._log_error(execution.id, None, str(exc))
            await self.broadcaster.broadcast(
                execution.id,
                {
                    "type": "execution_status",
                    "status": "failed",
                    "total_duration_ms": execution.total_duration_ms,
                    "error": str(exc),
                },
            )
            logger.error(
                "execution_failed",
                execution_id=str(execution.id),
                error=str(exc),
            )

        finally:
            await self.db.flush()

    async def _pause_for_review(
        self,
        execution: Execution,
        node: dict,
        ctx: ExecutionContext,
        step_index: int,
        execution_order: list[dict],
        sorter: TopoSorter,
        nodes_data: list[dict],
        edges_data: list[dict],
        input_data: dict,
        user_id: uuid.UUID,
        start_time: float,
        total_tokens: int,
    ) -> None:
        node_id = node["id"]
        node_type = node["type"]
        node_data = node.get("data", {})

        exec_node = ExecutionNode(
            id=uuid.uuid4(),
            execution_id=execution.id,
            node_id=node_id,
            node_type=node_type,
            status=NodeStatus.paused,
            input_data=ctx.get_node_inputs(node_id, node_data),
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(exec_node)
        await self.db.flush()

        await self.broadcaster.broadcast(
            execution.id,
            {
                "type": "node_status_change",
                "node_id": node_id,
                "status": "paused",
                "started_at": exec_node.started_at.isoformat(),
            },
        )
        await self.broadcaster.broadcast(
            execution.id,
            {
                "type": "review_request",
                "node_id": node_id,
                "input_data": exec_node.input_data,
            },
        )
        await self._log_info(
            execution.id,
            node_id,
            f"等待审核: {node_data.get('label', node_id)}",
        )

        checkpoint = {
            "start_index": step_index + 1,
            "context_state": ctx.export_state(),
            "skip_set": list(sorter.get_skip_set()),
            "start_time": start_time,
            "total_tokens": total_tokens,
            "nodes_data": nodes_data,
            "edges_data": edges_data,
            "input_data": input_data,
            "user_id": str(user_id),
            "review_node_id": node_id,
        }
        await self.redis.set(
            f"{CHECKPOINT_KEY_PREFIX}{execution.id}",
            json.dumps(checkpoint, ensure_ascii=False, default=str),
            ex=86400,
        )

        raise ReviewPausedException(node_id)

    async def _execute_node(
        self,
        execution: Execution,
        node: dict,
        ctx: ExecutionContext,
    ) -> dict:
        node_id = node["id"]
        node_type = node["type"]
        node_data = node.get("data", {})
        node_start = time.time()

        exec_node = ExecutionNode(
            id=uuid.uuid4(),
            execution_id=execution.id,
            node_id=node_id,
            node_type=node_type,
            status=NodeStatus.running,
            input_data=ctx.get_node_inputs(node_id, node_data),
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(exec_node)
        await self.db.flush()

        await self.broadcaster.broadcast(
            execution.id,
            {
                "type": "node_status_change",
                "node_id": node_id,
                "status": "running",
                "started_at": exec_node.started_at.isoformat(),
            },
        )
        await self._log_info(
            execution.id,
            node_id,
            f"开始执行节点: {node_data.get('label', node_id)} ({node_type})",
        )

        try:
            resolved_inputs = ctx.resolve_all_variables(node_data)
            executor = NodeExecutorRegistry.get_executor(node_type)

            if node_type == "parallelNode":
                result = await self._execute_parallel(execution, node, ctx)
            elif node_type == "loopNode":
                result = await self._execute_loop(execution, node, ctx)
            else:
                exec_result = await executor.execute(
                    config=node_data,
                    input_variables=resolved_inputs,
                    context=ctx,
                )
                result = {
                    "output": exec_result.output,
                    "tokens_used": exec_result.tokens_used,
                    "error": exec_result.error,
                }

            duration_ms = int((time.time() - node_start) * 1000)

            if result.get("error"):
                exec_node.status = NodeStatus.failed
                exec_node.error_message = result["error"]
                exec_node.duration_ms = duration_ms
                exec_node.finished_at = datetime.now(timezone.utc)

                await self.broadcaster.broadcast(
                    execution.id,
                    {
                        "type": "node_status_change",
                        "node_id": node_id,
                        "status": "failed",
                        "error": result["error"],
                        "duration_ms": duration_ms,
                        "finished_at": exec_node.finished_at.isoformat(),
                    },
                )
                await self._log_error(execution.id, node_id, result["error"])
            else:
                exec_node.status = NodeStatus.success
                exec_node.output_data = result.get("output", {})
                exec_node.duration_ms = duration_ms
                exec_node.tokens_used = result.get("tokens_used")
                exec_node.finished_at = datetime.now(timezone.utc)
                ctx.set_node_output(node_id, result.get("output", {}))

                await self.broadcaster.broadcast(
                    execution.id,
                    {
                        "type": "node_status_change",
                        "node_id": node_id,
                        "status": "success",
                        "output": result.get("output"),
                        "duration_ms": duration_ms,
                        "tokens_used": result.get("tokens_used"),
                        "finished_at": exec_node.finished_at.isoformat(),
                    },
                )
                await self._log_info(
                    execution.id,
                    node_id,
                    f"节点执行成功: {node_data.get('label', node_id)} "
                    f"(耗时 {duration_ms}ms)",
                )

            await self.db.flush()
            return result

        except Exception as exc:
            duration_ms = int((time.time() - node_start) * 1000)
            exec_node.status = NodeStatus.failed
            exec_node.error_message = str(exc)
            exec_node.duration_ms = duration_ms
            exec_node.finished_at = datetime.now(timezone.utc)
            await self.db.flush()

            await self.broadcaster.broadcast(
                execution.id,
                {
                    "type": "node_status_change",
                    "node_id": node_id,
                    "status": "failed",
                    "error": str(exc),
                    "duration_ms": duration_ms,
                    "finished_at": exec_node.finished_at.isoformat(),
                },
            )
            await self._log_error(execution.id, node_id, str(exc))
            raise ExecutionNodeError(str(exc), node_id=node_id) from exc

    async def _execute_parallel(
        self,
        execution: Execution,
        node: dict,
        ctx: ExecutionContext,
    ) -> dict:
        node_data = node.get("data", {})
        branches = node_data.get("branches", [])
        wait_mode = node_data.get("wait_mode", "all")

        branch_tasks = []
        for branch in branches:
            branch_id = branch["id"]
            branch_nodes = ctx.get_branch_nodes(node["id"], branch_id)
            branch_tasks.append(
                self._execute_branch(execution, branch_id, branch_nodes, ctx)
            )

        if not branch_tasks:
            return {"output": {"parallel_result": {}}, "tokens_used": None, "error": None}

        if wait_mode == "all":
            results = await asyncio.gather(*branch_tasks, return_exceptions=True)
        else:
            tasks = [asyncio.create_task(t) for t in branch_tasks]
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            results = []
            for t in done:
                try:
                    results.append(t.result())
                except Exception as exc:
                    results.append(exc)
            for t in pending:
                t.cancel()

        merged_output = {}
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                merged_output[f"branch_{i}_error"] = str(result)
            else:
                merged_output[f"branch_{i}"] = result

        return {
            "output": {"parallel_result": merged_output},
            "tokens_used": None,
            "error": None,
        }

    async def _execute_branch(
        self,
        execution: Execution,
        branch_id: str,
        branch_nodes: list[dict],
        ctx: ExecutionContext,
    ) -> dict:
        branch_output = {}
        for child_node in branch_nodes:
            if await self.cancellation_mgr.is_cancelled(execution.id):
                break
            result = await self._execute_node(execution, child_node, ctx)
            if result.get("output"):
                branch_output.update(result["output"])
        return branch_output

    async def _execute_loop(
        self,
        execution: Execution,
        node: dict,
        ctx: ExecutionContext,
    ) -> dict:
        node_data = node.get("data", {})
        loop_var_ref = node_data.get("loop_variable", "")
        item_name = node_data.get("item_name", "item")
        index_name = node_data.get("index_name", "index")

        resolver = VariableResolver()
        loop_array = resolver.resolve(loop_var_ref, ctx.variables)

        if not isinstance(loop_array, list):
            return {
                "output": {"error": "Loop variable is not an array"},
                "error": "Loop variable is not an array",
            }

        child_nodes = ctx.get_loop_child_nodes(node["id"])
        all_results = []

        for idx, item in enumerate(loop_array):
            if await self.cancellation_mgr.is_cancelled(execution.id):
                break

            ctx.set_iteration_variables(item_name, item, index_name, idx)
            iteration_output = {}
            for child_node in child_nodes:
                result = await self._execute_node(execution, child_node, ctx)
                if result.get("output"):
                    iteration_output.update(result["output"])

            all_results.append(
                {"index": idx, "item": item, "output": iteration_output}
            )
            ctx.clear_iteration_variables()

        return {
            "output": {
                "loop_results": all_results,
                "total_iterations": len(all_results),
            },
            "tokens_used": None,
            "error": None,
        }

    async def _skip_node(
        self,
        execution: Execution,
        node_id: str,
        node_type: str,
    ) -> None:
        exec_node = ExecutionNode(
            id=uuid.uuid4(),
            execution_id=execution.id,
            node_id=node_id,
            node_type=node_type,
            status=NodeStatus.skipped,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            duration_ms=0,
        )
        self.db.add(exec_node)
        await self.db.flush()

        await self.broadcaster.broadcast(
            execution.id,
            {
                "type": "node_status_change",
                "node_id": node_id,
                "status": "skipped",
            },
        )

    async def _handle_cancellation(
        self,
        execution: Execution,
        start_time: float,
        total_tokens: int,
    ) -> None:
        execution.status = ExecutionStatus.cancelled
        execution.total_duration_ms = int((time.time() - start_time) * 1000)
        execution.total_tokens = total_tokens
        execution.finished_at = datetime.now(timezone.utc)
        await self.db.flush()

        await self.broadcaster.broadcast(
            execution.id,
            {"type": "execution_status", "status": "cancelled"},
        )
        await self._log_info(execution.id, None, "执行已被用户取消")

    async def _log_info(
        self, execution_id: uuid.UUID, node_id: str | None, message: str
    ) -> None:
        await self._create_log(execution_id, node_id, LogLevel.info, message)

    async def _log_error(
        self, execution_id: uuid.UUID, node_id: str | None, message: str
    ) -> None:
        await self._create_log(execution_id, node_id, LogLevel.error, message)

    async def _create_log(
        self,
        execution_id: uuid.UUID,
        node_id: str | None,
        level: LogLevel,
        message: str,
    ) -> None:
        log = Log(
            id=uuid.uuid4(),
            execution_id=execution_id,
            node_id=node_id,
            level=level,
            message=message,
        )
        self.db.add(log)
        await self.db.flush()

        await self.broadcaster.broadcast(
            execution_id,
            {
                "type": "log",
                "level": level.value,
                "message": message,
                "node_id": node_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    @staticmethod
    def build_review_output(action: str, comment: str | None, modified_data: dict | None) -> dict:
        if action == "approve":
            return {
                "review_action": "approved",
                "review_comment": comment,
            }
        if action == "reject":
            return {
                "review_action": "rejected",
                "review_comment": comment,
            }
        if action == "modify":
            return modified_data or {}
        return {"review_action": action, "review_comment": comment}
