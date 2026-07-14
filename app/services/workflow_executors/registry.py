
from app.models.enums import NodeType
from .base import BaseNodeExecutor
from .agent_executor import AgentExecutor
from .knowledge_executor import KnowledgeRetrievalExecutor
from .code_executor import CodeExecutor
from .http_executor import HTTPExecutor
from .template_executor import TemplateExecutor
from .condition_executor import ConditionExecutor
from .classify_executor import ClassifyExecutor
from .extract_executor import ExtractExecutor
from .loop_executor import LoopExecutor
from .parallel_executor import ParallelExecutor
from .delay_executor import DelayExecutor
from .aggregate_executor import VariableAggregateExecutor
from .start_executor import StartExecutor
from .end_executor import EndExecutor
from .review_executor import ReviewExecutor
from .test_executor import TestExecutor


class NodeExecutorRegistry:
    """节点执行器注册表"""

    _executors: dict[str, type[BaseNodeExecutor]] = {
        NodeType.agent.value: AgentExecutor,
        NodeType.knowledge_retrieval.value: KnowledgeRetrievalExecutor,
        NodeType.code.value: CodeExecutor,
        NodeType.http.value: HTTPExecutor,
        NodeType.template.value: TemplateExecutor,
        NodeType.condition.value: ConditionExecutor,
        NodeType.classify.value: ClassifyExecutor,
        NodeType.extract.value: ExtractExecutor,
        NodeType.loop.value: LoopExecutor,
        NodeType.parallel.value: ParallelExecutor,
        NodeType.delay.value: DelayExecutor,
        NodeType.variable_aggregate.value: VariableAggregateExecutor,
        NodeType.start.value: StartExecutor,
        NodeType.end.value: EndExecutor,
        NodeType.review.value: ReviewExecutor,
        NodeType.test.value: TestExecutor,
    }

    @classmethod
    def get_executor(cls, node_type: str) -> BaseNodeExecutor:
        """获取节点类型的执行器实例"""
        executor_class = cls._executors.get(node_type)
        if executor_class is None:
            raise ValueError(f"Unsupported node type: {node_type}")
        return executor_class()
