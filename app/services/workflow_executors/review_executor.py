from typing import Any

from .base import BaseNodeExecutor, ExecutionContext, NodeExecutionResult


class ReviewExecutor(BaseNodeExecutor):
    """审核节点（单节点调试模式自动通过）。"""

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        return NodeExecutionResult(
            output={
                "review_action": "approved",
                "review_comment": "单节点调试模式自动通过",
            },
            duration_ms=0,
        )
