import pytest

from app.services.validation_service import ValidationService


@pytest.mark.asyncio
class TestWorkflowValidation:

    async def test_empty_canvas_invalid(self):
        issues = await ValidationService().validate_workflow([], [])
        codes = {i.code for i in issues}
        assert "NO_START_NODE" in codes
        assert "NO_END_NODE" in codes

    async def test_valid_minimal_workflow(self):
        nodes = [
            {
                "id": "start_1",
                "type": "startNode",
                "data": {"label": "开始", "outputs": [{"name": "user_query"}]},
            },
            {
                "id": "end_1",
                "type": "endNode",
                "data": {"label": "结束", "outputs": []},
            },
        ]
        edges = [{"source": "start_1", "target": "end_1"}]
        issues = await ValidationService().validate_workflow(nodes, edges)
        errors = [i for i in issues if i.level == "error"]
        assert len(errors) == 0

    async def test_missing_agent(self):
        nodes = [
            {"id": "start_1", "type": "startNode", "data": {"label": "开始"}},
            {"id": "agent_1", "type": "agentNode", "data": {"label": "Agent"}},
            {"id": "end_1", "type": "endNode", "data": {"label": "结束"}},
        ]
        edges = [
            {"source": "start_1", "target": "agent_1"},
            {"source": "agent_1", "target": "end_1"},
        ]
        issues = await ValidationService().validate_workflow(nodes, edges)
        assert any(i.code == "MISSING_AGENT" for i in issues)

    async def test_cycle_detected(self):
        nodes = [
            {"id": "a", "type": "startNode", "data": {}},
            {"id": "b", "type": "agentNode", "data": {"agent_id": "x"}},
            {"id": "c", "type": "endNode", "data": {}},
        ]
        edges = [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
            {"source": "c", "target": "b"},
        ]
        issues = await ValidationService().validate_workflow(nodes, edges)
        assert any(i.code == "CYCLE_DETECTED" for i in issues)
