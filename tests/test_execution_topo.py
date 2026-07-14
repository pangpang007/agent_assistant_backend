from app.services.execution.topo_sorter import TopoSorter


class TestTopoSorter:

    def test_linear_sort(self):
        nodes = [
            {"id": "A", "type": "startNode", "data": {}},
            {"id": "B", "type": "agentNode", "data": {}},
            {"id": "C", "type": "endNode", "data": {}},
        ]
        edges = [
            {"source": "A", "target": "B"},
            {"source": "B", "target": "C"},
        ]
        sorter = TopoSorter(nodes, edges)
        result = sorter.sort()
        assert [r["node"]["id"] for r in result] == ["A", "B", "C"]

    def test_parallel_sort(self):
        nodes = [
            {"id": "A", "type": "startNode", "data": {}},
            {"id": "B", "type": "agentNode", "data": {}},
            {"id": "C", "type": "agentNode", "data": {}},
            {"id": "D", "type": "endNode", "data": {}},
        ]
        edges = [
            {"source": "A", "target": "B"},
            {"source": "A", "target": "C"},
            {"source": "B", "target": "D"},
            {"source": "C", "target": "D"},
        ]
        sorter = TopoSorter(nodes, edges)
        result = sorter.sort()
        ids = [r["node"]["id"] for r in result]
        assert ids[0] == "A"
        assert set(ids[1:3]) == {"B", "C"}
        assert ids[3] == "D"

    def test_condition_skip(self):
        nodes = [
            {"id": "A", "type": "conditionNode", "data": {}},
            {"id": "B", "type": "agentNode", "data": {}},
            {"id": "C", "type": "agentNode", "data": {}},
        ]
        edges = [
            {"source": "A", "target": "B", "sourceHandle": "branch_true"},
            {"source": "A", "target": "C", "sourceHandle": "branch_false"},
        ]
        sorter = TopoSorter(nodes, edges)
        sorter.mark_branch_result("A", "branch_true", edges)
        assert sorter.should_skip("C")
        assert not sorter.should_skip("B")
