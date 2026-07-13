
import re
import time
from typing import Any

from .base import BaseNodeExecutor, NodeExecutionResult, ExecutionContext


class ConditionExecutor(BaseNodeExecutor):
    """
    条件分支节点执行器：评估条件表达式，返回匹配的分支 ID。
    
    支持的操作符:
    - equals / not_equals: 精确匹配
    - contains / not_contains: 包含/不包含
    - starts_with / ends_with: 前缀/后缀匹配
    - regex: 正则匹配
    - is_empty / is_not_empty: 空/非空
    - gt / gte / lt / lte: 数值比较
    """

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()

        try:
            conditions = config.get("conditions", [])
            branches = config.get("branches", [])

            if not conditions:
                return NodeExecutionResult(error="No conditions defined", duration_ms=self._elapsed(start_time))

            # 逐个评估条件
            matched_branch_id = None
            for condition in conditions:
                variable_ref = condition.get("variable", "")
                operator = condition.get("operator", "equals")
                expected = condition.get("value")

                # 解析变量值
                actual = self._resolve_variable_ref(variable_ref, input_variables)

                # 评估条件
                if self._evaluate(actual, operator, expected):
                    # 找到对应的分支
                    cond_id = condition.get("id")
                    for branch in branches:
                        if branch.get("condition_id") == cond_id:
                            matched_branch_id = branch["id"]
                            break
                    break  # 第一个匹配的条件

            # 如果没有匹配任何条件，走默认分支
            if not matched_branch_id:
                for branch in branches:
                    if branch.get("condition_id") is None:
                        matched_branch_id = branch["id"]
                        break

            return NodeExecutionResult(
                output={"matched_branch": matched_branch_id},
                duration_ms=self._elapsed(start_time),
            )

        except Exception as e:
            return NodeExecutionResult(error=str(e), duration_ms=self._elapsed(start_time))

    def _resolve_variable_ref(self, ref: str, variables: dict) -> Any:
        """解析变量引用，支持 ${...} 格式"""
        if isinstance(ref, str) and ref.startswith("${") and ref.endswith("}"):
            var_name = ref[2:-1]
            return variables.get(var_name)
        return ref

    def _evaluate(self, actual: Any, operator: str, expected: Any) -> bool:
        """评估单个条件"""
        if operator == "equals":
            return str(actual) == str(expected)
        elif operator == "not_equals":
            return str(actual) != str(expected)
        elif operator == "contains":
            return str(expected) in str(actual)
        elif operator == "not_contains":
            return str(expected) not in str(actual)
        elif operator == "starts_with":
            return str(actual).startswith(str(expected))
        elif operator == "ends_with":
            return str(actual).endswith(str(expected))
        elif operator == "regex":
            return bool(re.search(str(expected), str(actual)))
        elif operator == "is_empty":
            return actual is None or str(actual).strip() == ""
        elif operator == "is_not_empty":
            return actual is not None and str(actual).strip() != ""
        elif operator == "gt":
            return float(actual) > float(expected)
        elif operator == "gte":
            return float(actual) >= float(expected)
        elif operator == "lt":
            return float(actual) < float(expected)
        elif operator == "lte":
            return float(actual) <= float(expected)
        else:
            return False

    def _elapsed(self, start_time) -> int:
        return int((time.time() - start_time) * 1000)
