"""问题分类节点执行器（单节点调试简化实现）。"""

import time
from typing import Any

from .base import BaseNodeExecutor, ExecutionContext, NodeExecutionResult


class ClassifyExecutor(BaseNodeExecutor):
    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()
        categories = config.get("categories", [])
        text = ""
        for v in input_variables.values():
            text += str(v) + " "
        matched = categories[0] if categories else {"id": "default", "label": "默认"}
        for cat in categories:
            for kw in cat.get("keywords", []):
                if kw.lower() in text.lower():
                    matched = cat
                    break
        return NodeExecutionResult(
            output={
                "category_id": matched.get("id"),
                "category_label": matched.get("label"),
            },
            duration_ms=int((time.time() - start_time) * 1000),
        )
