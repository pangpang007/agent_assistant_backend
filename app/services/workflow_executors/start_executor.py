from typing import Any

from .base import BaseNodeExecutor, ExecutionContext, NodeExecutionResult


class StartExecutor(BaseNodeExecutor):
    """开始节点：校验并透传全局输入参数。"""

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        node_inputs = config.get("inputs", [])
        global_input = getattr(context, "_global_input", None) or input_variables
        output = {}

        for input_def in node_inputs:
            name = input_def["name"]
            required = input_def.get("required", False)
            default_value = input_def.get("default_value")

            value = global_input.get(name)
            if value is None and name in input_variables:
                value = input_variables.get(name)
            if value is None and f"input.{name}" in input_variables:
                value = input_variables.get(f"input.{name}")

            if value is None:
                if required:
                    return NodeExecutionResult(
                        error=f"缺少必填输入参数: {name}",
                        duration_ms=0,
                    )
                value = default_value

            output[name] = value

        if not node_inputs:
            output = dict(global_input) if isinstance(global_input, dict) else {}

        return NodeExecutionResult(output=output, duration_ms=0)
