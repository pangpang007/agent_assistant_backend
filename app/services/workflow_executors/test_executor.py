import time
from typing import Any

from app.services.execution.variable_resolver import VariableResolver

from .base import BaseNodeExecutor, ExecutionContext, NodeExecutionResult
from .condition_executor import ConditionExecutor


class TestExecutor(BaseNodeExecutor):
    """测试节点：断言校验。"""

    def __init__(self):
        self._condition = ConditionExecutor()

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()

        assertions = config.get("assertions", [])
        on_failure = config.get("on_failure", "continue")
        resolver = VariableResolver()

        results = []
        all_passed = True

        for assertion in assertions:
            variable_ref = assertion.get("variable", "")
            operator = assertion.get("operator", "is_not_empty")
            expected = assertion.get("expected")

            actual = resolver.resolve(variable_ref, input_variables)
            passed = self._condition._evaluate(actual, operator, expected)

            results.append(
                {
                    "variable": variable_ref,
                    "operator": operator,
                    "expected": expected,
                    "actual": actual,
                    "passed": passed,
                }
            )
            if not passed:
                all_passed = False

        output = {
            "test_results": results,
            "all_passed": all_passed,
            "passed_count": sum(1 for r in results if r["passed"]),
            "failed_count": sum(1 for r in results if not r["passed"]),
        }

        if not all_passed:
            if on_failure == "abort":
                return NodeExecutionResult(
                    output=output,
                    duration_ms=self._elapsed(start_time),
                    error=f"测试失败: {output['failed_count']} 个断言未通过",
                )
            if on_failure == "retry":
                output["retry_requested"] = True
                output["retry_count"] = config.get("retry_count", 3)

        return NodeExecutionResult(output=output, duration_ms=self._elapsed(start_time))

    def _elapsed(self, start_time: float) -> int:
        return int((time.time() - start_time) * 1000)
