"""延时节点执行器。"""

import asyncio
import time
from typing import Any

from .base import BaseNodeExecutor, ExecutionContext, NodeExecutionResult


class DelayExecutor(BaseNodeExecutor):
    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()
        delay = min(int(config.get("delay_seconds", 1)), 5)
        await asyncio.sleep(delay)
        return NodeExecutionResult(
            output={"delayed_seconds": delay},
            duration_ms=int((time.time() - start_time) * 1000),
        )
