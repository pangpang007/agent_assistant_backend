
import time
from typing import Any, Optional
from abc import ABC, abstractmethod


class ExecutionContext:
    """节点执行上下文"""
    def __init__(
        self,
        workflow_id: str,
        user_id: str,
        db_session,       # AsyncSession
        redis_client,     # Redis
    ):
        self.workflow_id = workflow_id
        self.user_id = user_id
        self.db_session = db_session
        self.redis_client = redis_client


class NodeExecutionResult:
    """节点执行结果"""
    def __init__(
        self,
        output: Any = None,
        duration_ms: int = 0,
        tokens_used: Optional[int] = None,
        error: Optional[str] = None,
    ):
        self.output = output
        self.duration_ms = duration_ms
        self.tokens_used = tokens_used
        self.error = error


class BaseNodeExecutor(ABC):
    """节点执行器基类"""

    # 默认超时时间（秒）
    DEFAULT_TIMEOUT = 30

    @abstractmethod
    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        """
        执行节点逻辑。
        
        Args:
            config: 节点配置（来自 node.data）
            input_variables: 输入变量（键已解析为实际值）
            context: 执行上下文
        
        Returns:
            NodeExecutionResult
        """
        pass

    def _resolve_timeout(self, config: dict) -> int:
        """从配置中获取超时时间，有默认值"""
        return config.get("timeout", self.DEFAULT_TIMEOUT)

    def _resolve_variables(self, mapping: dict, input_variables: dict) -> dict:
        """
        根据 input_mapping 解析输入变量。
        
        mapping 示例: {"query": "${input.user_query}"}
        input_variables 示例: {"input.user_query": "hello"}
        返回: {"query": "hello"}
        """
        resolved = {}
        for key, template in mapping.items():
            if isinstance(template, str) and template.startswith("${") and template.endswith("}"):
                var_ref = template[2:-1]  # 去掉 ${ 和 }
                resolved[key] = input_variables.get(var_ref, template)
            else:
                resolved[key] = template
        return resolved
