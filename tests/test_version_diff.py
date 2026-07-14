from app.services.version_service import deep_diff, diff_edges, diff_nodes


class TestDeepDiff:
    def test_added_and_removed_and_modified(self):
        old = {"a": 1, "b": {"x": 1}, "c": [1, 2]}
        new = {"a": 2, "b": {"x": 2, "y": 3}, "d": True}
        changes = deep_diff(old, new)
        by_field = {c["field"]: c for c in changes}

        assert by_field["a"]["change_type"] == "modified"
        assert by_field["a"]["old_value"] == 1
        assert by_field["a"]["new_value"] == 2
        assert by_field["c"]["change_type"] == "removed"
        assert by_field["d"]["change_type"] == "added"
        assert by_field["b.x"]["change_type"] == "modified"
        assert by_field["b.y"]["change_type"] == "added"


class TestDiffNodes:
    def test_add_remove_modify(self):
        v1 = [
            {
                "id": "n1",
                "type": "startNode",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Start", "agent_id": "a1"},
            },
            {
                "id": "n2",
                "type": "agentNode",
                "position": {"x": 100, "y": 0},
                "data": {"label": "Agent", "temperature": 0.7},
            },
        ]
        v2 = [
            {
                "id": "n1",
                "type": "startNode",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Start", "agent_id": "a2"},
            },
            {
                "id": "n3",
                "type": "endNode",
                "position": {"x": 200, "y": 0},
                "data": {"label": "End"},
            },
        ]

        result = diff_nodes(v1, v2)
        assert {n["id"] for n in result["added"]} == {"n3"}
        assert {n["id"] for n in result["removed"]} == {"n2"}
        assert len(result["modified"]) == 1
        assert result["modified"][0]["id"] == "n1"
        fields = {c["field"] for c in result["modified"][0]["changes"]}
        assert "agent_id" in fields


class TestDiffEdges:
    def test_add_remove_modify(self):
        v1 = [
            {
                "id": "e1",
                "source": "n1",
                "target": "n2",
                "sourceHandle": "out",
                "type": "default",
                "data": {},
            },
            {
                "id": "e2",
                "source": "n2",
                "target": "n3",
                "sourceHandle": "out",
                "type": "default",
                "data": {"weight": 1},
            },
        ]
        v2 = [
            {
                "id": "e1",
                "source": "n1",
                "target": "n2",
                "sourceHandle": "out",
                "type": "smoothstep",
                "data": {},
            },
            {
                "id": "e3",
                "source": "n1",
                "target": "n3",
                "sourceHandle": "out",
                "type": "default",
                "data": {},
            },
        ]

        result = diff_edges(v1, v2)
        assert len(result["added"]) == 1
        assert result["added"][0]["source"] == "n1"
        assert result["added"][0]["target"] == "n3"
        assert len(result["removed"]) == 1
        assert result["removed"][0]["target"] == "n3"
        assert len(result["modified"]) == 1
        assert result["modified"][0]["id"] == "e1"
