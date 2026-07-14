from collections import deque
from typing import Optional


class TopoSorter:
    """
    工作流拓扑排序器（Kahn 算法）。
    支持条件分支跳过标记。
    """

    def __init__(self, nodes_data: list[dict], edges_data: list[dict]):
        self.nodes_data = nodes_data
        self.edges_data = edges_data
        self._node_map = {n["id"]: n for n in nodes_data}
        self._skip_set: set[str] = set()

    def sort(self) -> list[dict]:
        node_ids = {n["id"] for n in self.nodes_data}

        adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}

        for edge in self.edges_data:
            source = edge.get("source")
            target = edge.get("target")
            if source in node_ids and target in node_ids:
                adjacency[source].append(target)
                in_degree[target] = in_degree.get(target, 0) + 1

        result = []
        depth = 0
        queue = deque([nid for nid in node_ids if in_degree[nid] == 0])

        while queue:
            layer_size = len(queue)
            for _ in range(layer_size):
                nid = queue.popleft()
                node = self._node_map.get(nid)
                if node:
                    result.append(
                        {
                            "node": node,
                            "depth": depth,
                            "group": self._determine_group(nid),
                            "skip": False,
                        }
                    )

                for neighbor in adjacency.get(nid, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            depth += 1

        return result

    def _determine_group(self, node_id: str) -> Optional[str]:
        for edge in self.edges_data:
            if edge.get("target") == node_id:
                source_node = self._node_map.get(edge.get("source"))
                if source_node:
                    if source_node["type"] == "parallelNode":
                        return f"parallel_{edge['source']}"
                    if source_node["type"] == "loopNode":
                        return f"loop_{edge['source']}"
        return None

    def mark_branch_result(
        self,
        condition_node_id: str,
        matched_branch_id: Optional[str],
        edges_data: list[dict],
    ) -> None:
        condition_edges = [
            e for e in edges_data if e.get("source") == condition_node_id
        ]

        for edge in condition_edges:
            source_handle = edge.get("sourceHandle", "")
            if source_handle != matched_branch_id:
                target_id = edge.get("target")
                if target_id:
                    self._mark_downstream_skip(target_id, edges_data)

    def _mark_downstream_skip(self, start_id: str, edges_data: list[dict]) -> None:
        queue = deque([start_id])
        visited: set[str] = set()

        while queue:
            nid = queue.popleft()
            if nid in visited:
                continue
            visited.add(nid)
            self._skip_set.add(nid)

            for edge in edges_data:
                if edge.get("source") == nid:
                    target = edge.get("target")
                    if target:
                        queue.append(target)

    def should_skip(self, node_id: str) -> bool:
        return node_id in self._skip_set

    def get_skip_set(self) -> set[str]:
        return set(self._skip_set)

    def restore_skip_set(self, skip_set: set[str]) -> None:
        self._skip_set = set(skip_set)
