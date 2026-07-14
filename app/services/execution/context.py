import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_value
from app.models.env_variable import EnvVariable
from app.services.execution.variable_resolver import VariableResolver


class ExecutionContext:
    """工作流执行上下文（Phase 5）。"""

    def __init__(
        self,
        execution_id: uuid.UUID,
        workflow_id: uuid.UUID,
        user_id: uuid.UUID,
        db_session: AsyncSession,
        redis_client,
        broadcaster=None,
        cancellation_mgr=None,
        review_mgr=None,
    ):
        self.execution_id = execution_id
        self.workflow_id = workflow_id
        self.user_id = user_id
        self.db_session = db_session
        self.redis_client = redis_client
        self.broadcaster = broadcaster
        self.cancellation_mgr = cancellation_mgr
        self.review_mgr = review_mgr

        self._global_input: dict[str, Any] = {}
        self._node_outputs: dict[str, dict[str, Any]] = {}
        self._iteration_vars: dict[str, Any] = {}
        self._env_cache: dict[str, str] = {}

        self._nodes_data: list[dict] = []
        self._edges_data: list[dict] = []
        self._node_map: dict[str, dict] = {}

    def set_graph(self, nodes_data: list[dict], edges_data: list[dict]) -> None:
        self._nodes_data = nodes_data
        self._edges_data = edges_data
        self._node_map = {n["id"]: n for n in nodes_data}

    def set_global_input(self, input_data: dict[str, Any]) -> None:
        self._global_input = input_data

    def set_node_output(self, node_id: str, output: dict[str, Any]) -> None:
        self._node_outputs[node_id] = output or {}

    def get_node_output(self, node_id: str) -> dict[str, Any]:
        return self._node_outputs.get(node_id, {})

    def set_iteration_variables(
        self, item_name: str, item: Any, index_name: str, index: int
    ) -> None:
        self._iteration_vars[item_name] = item
        self._iteration_vars[index_name] = index

    def clear_iteration_variables(self) -> None:
        self._iteration_vars.clear()

    def restore_state(
        self,
        global_input: dict[str, Any],
        node_outputs: dict[str, dict[str, Any]],
    ) -> None:
        self._global_input = global_input
        self._node_outputs = node_outputs

    def export_state(self) -> dict[str, Any]:
        return {
            "global_input": self._global_input,
            "node_outputs": self._node_outputs,
        }

    @property
    def variables(self) -> dict[str, Any]:
        all_vars: dict[str, Any] = {}

        for key, value in self._global_input.items():
            all_vars[f"input.{key}"] = value

        for node_id, outputs in self._node_outputs.items():
            for var_name, value in outputs.items():
                all_vars[f"{node_id}.{var_name}"] = value

        all_vars.update(self._iteration_vars)
        return all_vars

    def resolve_variable(self, ref: str) -> Any:
        if ref.startswith("${") and ref.endswith("}"):
            var_path = ref[2:-1]
        else:
            var_path = ref

        if var_path.startswith("env."):
            env_key = var_path[4:]
            return self._env_cache.get(env_key)

        return self.variables.get(var_path)

    def resolve_all_variables(self, node_data: dict) -> dict[str, Any]:
        return self.variables

    def get_node_inputs(self, node_id: str, node_data: dict) -> dict[str, Any]:
        input_mapping = node_data.get("input_mapping", {})
        resolved = {}
        resolver = VariableResolver()
        for key, template in input_mapping.items():
            resolved[key] = resolver.resolve(template, self.variables)
        return resolved

    def get_end_outputs(self) -> dict[str, Any]:
        end_outputs = {}
        resolver = VariableResolver()
        for node in self._nodes_data:
            if node["type"] == "endNode":
                output_mapping = node.get("data", {}).get("output_mapping", {})
                for key, template in output_mapping.items():
                    end_outputs[key] = resolver.resolve(template, self.variables)
        return end_outputs

    def get_branch_nodes(self, parallel_node_id: str, branch_id: str) -> list[dict]:
        branch_edges = [
            e
            for e in self._edges_data
            if e.get("source") == parallel_node_id
            and e.get("sourceHandle") == branch_id
        ]
        result = []
        visited: set[str] = set()
        queue = [e["target"] for e in branch_edges]

        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            if nid in self._node_map:
                result.append(self._node_map[nid])
            for edge in self._edges_data:
                if edge["source"] == nid:
                    queue.append(edge["target"])

        return result

    def get_loop_child_nodes(self, loop_node_id: str) -> list[dict]:
        loop_edges = [
            e for e in self._edges_data if e.get("source") == loop_node_id
        ]
        result = []
        visited: set[str] = set()
        queue = [e["target"] for e in loop_edges]

        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            if nid in self._node_map:
                result.append(self._node_map[nid])
            for edge in self._edges_data:
                if edge["source"] == nid:
                    queue.append(edge["target"])

        return result

    async def resolve_env_in_value(self, value: Any) -> Any:
        """递归解析值中的环境变量引用。"""

        async def env_resolver(key: str) -> Optional[str]:
            return await self._get_env_variable(key)

        resolver = VariableResolver()

        if isinstance(value, str) and "${env." in value:
            env_key = None
            if value.startswith("${env.") and value.endswith("}"):
                env_key = value[6:-1]
            if env_key:
                resolved = await self._get_env_variable(env_key)
                return resolved if resolved is not None else value

        return await self._resolve_env_async(value, env_resolver, resolver)

    async def _resolve_env_async(
        self,
        template: Any,
        env_resolver,
        resolver: VariableResolver,
    ) -> Any:
        if isinstance(template, str):
            if "${env." not in template:
                return template

            result = template
            for match in resolver.VAR_PATTERN.findall(template):
                if match.startswith("env."):
                    env_key = match[4:]
                    value = await env_resolver(env_key)
                    if value is not None:
                        result = result.replace(f"${{{match}}}", value)
            return result
        if isinstance(template, dict):
            return {
                k: await self._resolve_env_async(v, env_resolver, resolver)
                for k, v in template.items()
            }
        if isinstance(template, list):
            return [
                await self._resolve_env_async(item, env_resolver, resolver)
                for item in template
            ]
        return template

    async def _get_env_variable(self, key: str) -> Optional[str]:
        if key in self._env_cache:
            return self._env_cache[key]

        result = await self.db_session.execute(
            select(EnvVariable).where(
                EnvVariable.user_id == self.user_id,
                EnvVariable.key == key,
            )
        )
        env_var = result.scalar_one_or_none()
        if env_var:
            value = decrypt_value(env_var.value_encrypted)
            self._env_cache[key] = value
            return value
        return None
