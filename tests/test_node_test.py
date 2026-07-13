import pytest

from app.services.workflow_executors.condition_executor import ConditionExecutor
from app.services.workflow_executors.base import ExecutionContext
from app.services.workflow_executors.template_executor import TemplateExecutor


@pytest.mark.asyncio
class TestNodeExecutors:

    async def test_template_executor(self):
        executor = TemplateExecutor()
        ctx = ExecutionContext("wf", "user", None, None)
        result = await executor.execute(
            {
                "template": "Hello {{ name }}",
                "input_mapping": {"name": "${start.name}"},
                "output_key": "text",
            },
            {"start.name": "World"},
            ctx,
        )
        assert result.error is None
        assert result.output["text"] == "Hello World"

    async def test_condition_executor_equals(self):
        executor = ConditionExecutor()
        ctx = ExecutionContext("wf", "user", None, None)
        result = await executor.execute(
            {
                "conditions": [
                    {
                        "id": "c1",
                        "variable": "${agent.result}",
                        "operator": "equals",
                        "value": "ok",
                    }
                ],
                "branches": [
                    {"id": "true_branch", "condition_id": "c1"},
                    {"id": "false_branch", "condition_id": None},
                ],
            },
            {"agent.result": "ok"},
            ctx,
        )
        assert result.error is None
        assert result.output["matched_branch"] == "true_branch"
