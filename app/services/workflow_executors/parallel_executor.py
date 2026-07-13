"""并行节点执行器（调试模式返回模拟结果）。"""

import time
from typing import Any

from .base import BaseNodeExecutor, ExecutionContext, NodeExecutionResult


class ParallelExecutor(BaseNodeExecutor):
    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()
        branches = config.get("branches", [])
        return NodeExecutionResult(
            output={
                "parallel_status": "simulated",
                "branches": [b.get("id") for b in branches],
            },
            duration_ms=int((time.time() - start_time) * 1000),
        )
