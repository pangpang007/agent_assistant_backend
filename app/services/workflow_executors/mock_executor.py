"""模拟执行器：用于 start/end/review/test 等节点。"""

from typing import Any

from .base import BaseNodeExecutor, ExecutionContext, NodeExecutionResult


class MockExecutor(BaseNodeExecutor):
    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        return NodeExecutionResult(
            output={"mock": True, "input_variables": input_variables},
            duration_ms=0,
        )
