"""变量聚合节点执行器。"""

import time
from typing import Any

from .base import BaseNodeExecutor, ExecutionContext, NodeExecutionResult


class VariableAggregateExecutor(BaseNodeExecutor):
    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()
        result = {}
        for agg in config.get("aggregations", []):
            name = agg.get("name", "unnamed")
            sources = agg.get("sources", [])
            mode = agg.get("mode", "array")
            values = []
            for src in sources:
                if isinstance(src, str) and src.startswith("${") and src.endswith("}"):
                    var_name = src[2:-1]
                    values.append(input_variables.get(var_name))
                else:
                    values.append(src)
            if mode == "array":
                result[name] = values
            elif mode == "concat":
                result[name] = "".join(str(v) for v in values)
            elif mode == "merge":
                merged = {}
                for v in values:
                    if isinstance(v, dict):
                        merged.update(v)
                result[name] = merged
        output_key = config.get("output_key", "aggregated")
        return NodeExecutionResult(
            output={output_key: result},
            duration_ms=int((time.time() - start_time) * 1000),
        )
