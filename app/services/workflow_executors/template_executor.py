
import time
from typing import Any
from jinja2 import Environment, BaseLoader, sandbox

from .base import BaseNodeExecutor, NodeExecutionResult, ExecutionContext


class TemplateExecutor(BaseNodeExecutor):
    """
    模板转换节点执行器：使用 Jinja2 渲染模板。
    
    执行流程：
    1. 获取模板字符串
    2. 解析 input_mapping 中的变量
    3. 使用 Jinja2 SandboxEnvironment 渲染
    4. 返回渲染结果
    """

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()

        try:
            template_str = config.get("template", "")
            if not template_str:
                return NodeExecutionResult(error="Template is empty", duration_ms=self._elapsed(start_time))

            # 解析输入变量
            input_mapping = config.get("input_mapping", {})
            resolved_vars = self._resolve_variables(input_mapping, input_variables)

            # 使用沙箱环境渲染（防止模板注入攻击）
            env = sandbox.SandboxedEnvironment(loader=BaseLoader())
            template = env.from_string(template_str)
            rendered = template.render(**resolved_vars)

            output_key = config.get("output_key", "rendered_text")
            return NodeExecutionResult(
                output={output_key: rendered},
                duration_ms=self._elapsed(start_time),
            )

        except Exception as e:
            return NodeExecutionResult(error=f"Template rendering failed: {str(e)}", duration_ms=self._elapsed(start_time))

    def _elapsed(self, start_time) -> int:
        return int((time.time() - start_time) * 1000)
