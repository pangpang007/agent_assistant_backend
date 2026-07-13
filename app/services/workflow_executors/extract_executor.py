"""参数提取节点执行器（单节点调试简化实现）。"""

import time
from typing import Any

from .base import BaseNodeExecutor, ExecutionContext, NodeExecutionResult


class ExtractExecutor(BaseNodeExecutor):
    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()
        extracted = {}
        for field in config.get("extraction_schema", []):
            name = field.get("name")
            if name:
                extracted[name] = input_variables.get(name)
        output_key = config.get("output_key", "extracted_params")
        return NodeExecutionResult(
            output={output_key: extracted},
            duration_ms=int((time.time() - start_time) * 1000),
        )
