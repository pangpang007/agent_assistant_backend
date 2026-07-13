"""循环节点执行器（调试模式仅模拟一次迭代）。"""

import time
from typing import Any

from .base import BaseNodeExecutor, ExecutionContext, NodeExecutionResult


class LoopExecutor(BaseNodeExecutor):
    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()
        loop_var = config.get("loop_variable", "")
        items = input_variables.get(loop_var.strip("${}"), [])
        if isinstance(items, str):
            items = [items]
        item_name = config.get("item_name", "current_item")
        index_name = config.get("index_name", "current_index")
        current = items[0] if items else None
        return NodeExecutionResult(
            output={item_name: current, index_name: 0},
            duration_ms=int((time.time() - start_time) * 1000),
        )
