from typing import Any

from app.services.execution.variable_resolver import VariableResolver

from .base import BaseNodeExecutor, ExecutionContext, NodeExecutionResult


class EndExecutor(BaseNodeExecutor):
    """结束节点：解析 output_mapping 生成最终输出。"""

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        output_mapping = config.get("output_mapping", {})
        resolver = VariableResolver()

        output = {}
        for key, template in output_mapping.items():
            output[key] = resolver.resolve(template, input_variables)

        return NodeExecutionResult(output=output, duration_ms=0)
