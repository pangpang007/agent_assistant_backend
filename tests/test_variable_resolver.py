from app.services.execution.variable_resolver import VariableResolver


class TestVariableResolver:

    def test_single_reference(self):
        resolver = VariableResolver()
        assert resolver.resolve("${node_1.result}", {"node_1.result": "hello"}) == "hello"
        assert resolver.resolve("${node_1.count}", {"node_1.count": 42}) == 42
        assert resolver.resolve("${node_1.data}", {"node_1.data": {"key": "val"}}) == {
            "key": "val"
        }

    def test_mixed_text(self):
        resolver = VariableResolver()
        result = resolver.resolve("Hello ${node_1.name}!", {"node_1.name": "World"})
        assert result == "Hello World!"

    def test_dict_resolution(self):
        resolver = VariableResolver()
        result = resolver.resolve({"key": "${node_1.value}"}, {"node_1.value": 123})
        assert result == {"key": 123}

    def test_list_resolution(self):
        resolver = VariableResolver()
        result = resolver.resolve(["${a.x}", "${b.y}"], {"a.x": 1, "b.y": 2})
        assert result == [1, 2]

    def test_unresolved_reference(self):
        resolver = VariableResolver()
        result = resolver.resolve("${node_x.missing}", {})
        assert result == "${node_x.missing}"

    def test_env_variable(self):
        resolver = VariableResolver()
        result = resolver.resolve("${env.API_KEY}", {})
        assert result == "${env.API_KEY}"

    def test_extract_refs(self):
        resolver = VariableResolver()
        refs = resolver.extract_refs(
            {
                "a": "${node_1.x}",
                "b": "text ${node_2.y} more ${node_3.z}",
                "c": [1, "${env.SECRET}"],
            }
        )
        assert set(refs) == {"node_1.x", "node_2.y", "node_3.z", "env.SECRET"}
