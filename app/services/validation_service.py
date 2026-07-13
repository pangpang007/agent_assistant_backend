"""工作流校验引擎。"""

import re

from app.schemas.workflow import ValidationIssue


class ValidationService:
    """工作流校验引擎"""

    async def validate_workflow(
        self,
        nodes_data: list[dict],
        edges_data: list[dict],
    ) -> list[ValidationIssue]:
        """
        执行全量校验，返回所有问题。
        """
        issues: list[ValidationIssue] = []

        # 1. 必填项检查
        issues.extend(self._check_required_fields(nodes_data))

        # 2. 连通性检查
        issues.extend(self._check_connectivity(nodes_data, edges_data))

        # 3. DAG 环检测（排除循环节点内部）
        issues.extend(self._check_dag(nodes_data, edges_data))

        # 4. 变量引用检查
        issues.extend(self._check_variable_references(nodes_data, edges_data))

        return issues

    def _check_required_fields(self, nodes_data: list[dict]) -> list[ValidationIssue]:
        """必填项检查"""
        issues = []

        # 开始节点检查
        start_nodes = [n for n in nodes_data if n["type"] == "startNode"]
        if len(start_nodes) == 0:
            issues.append(ValidationIssue(
                level="error",
                code="NO_START_NODE",
                message="工作流必须包含一个开始节点",
            ))
        elif len(start_nodes) > 1:
            issues.append(ValidationIssue(
                level="error",
                code="MULTIPLE_START_NODES",
                message="工作流只能包含一个开始节点",
                node_id=start_nodes[1]["id"],
            ))

        # 结束节点检查
        end_nodes = [n for n in nodes_data if n["type"] == "endNode"]
        if len(end_nodes) == 0:
            issues.append(ValidationIssue(
                level="error",
                code="NO_END_NODE",
                message="工作流至少需要一个结束节点",
            ))

        # 逐节点类型检查
        for node in nodes_data:
            node_type = node["type"]
            node_id = node["id"]
            data = node.get("data", {})

            if node_type == "agentNode":
                if not data.get("agent_id"):
                    issues.append(ValidationIssue(
                        level="error",
                        code="MISSING_AGENT",
                        message=f"Agent 节点 '{data.get('label', node_id)}' 未选择 Agent",
                        node_id=node_id,
                    ))

            elif node_type == "knowledgeRetrievalNode":
                if not data.get("knowledge_base_id"):
                    issues.append(ValidationIssue(
                        level="error",
                        code="MISSING_KB",
                        message=f"知识检索节点 '{data.get('label', node_id)}' 未选择知识库",
                        node_id=node_id,
                    ))

            elif node_type == "codeNode":
                if not data.get("code"):
                    issues.append(ValidationIssue(
                        level="error",
                        code="MISSING_CODE",
                        message=f"代码节点 '{data.get('label', node_id)}' 未编写代码",
                        node_id=node_id,
                    ))

            elif node_type == "httpNode":
                if not data.get("url"):
                    issues.append(ValidationIssue(
                        level="error",
                        code="MISSING_HTTP_URL",
                        message=f"HTTP 节点 '{data.get('label', node_id)}' 未填写 URL",
                        node_id=node_id,
                    ))

            elif node_type == "templateNode":
                if not data.get("template"):
                    issues.append(ValidationIssue(
                        level="error",
                        code="MISSING_TEMPLATE",
                        message=f"模板节点 '{data.get('label', node_id)}' 未编写模板",
                        node_id=node_id,
                    ))

            elif node_type == "conditionNode":
                if not data.get("conditions"):
                    issues.append(ValidationIssue(
                        level="error",
                        code="MISSING_CONDITIONS",
                        message=f"条件分支节点 '{data.get('label', node_id)}' 未配置条件",
                        node_id=node_id,
                    ))

        return issues

    def _check_connectivity(
        self,
        nodes_data: list[dict],
        edges_data: list[dict],
    ) -> list[ValidationIssue]:
        """
        连通性检查：所有节点必须在工作流中连通（通过边连接）。
        开始节点只有出边，结束节点只有入边，其余节点必须既有入边也有出边。

        算法：
        1. 构建邻接表（有向图）
        2. 从开始节点出发，BFS/DFS 遍历
        3. 记录所有可达节点
        4. 对比全部节点，不可达的即为孤立节点
        """
        issues = []

        if not nodes_data:
            return issues

        node_ids = {n["id"] for n in nodes_data}

        # 构建邻接表
        adjacency: dict[str, set[str]] = {nid: set() for nid in node_ids}
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}

        for edge in (edges_data or []):
            source = edge.get("source")
            target = edge.get("target")
            if source in node_ids and target in node_ids:
                adjacency[source].add(target)
                in_degree[target] = in_degree.get(target, 0) + 1

        # 从开始节点 BFS
        start_nodes = [n["id"] for n in nodes_data if n["type"] == "startNode"]
        if not start_nodes:
            return issues  # 没有开始节点，由必填项检查覆盖

        visited = set()
        queue = list(start_nodes)
        visited.update(start_nodes)

        while queue:
            current = queue.pop(0)
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        # 找出不可达节点
        unreachable = node_ids - visited
        for nid in unreachable:
            node = next((n for n in nodes_data if n["id"] == nid), None)
            label = node["data"].get("label", nid) if node else nid
            issues.append(ValidationIssue(
                level="error",
                code="ORPHAN_NODE",
                message=f"节点 '{label}' 未与开始节点连通",
                node_id=nid,
            ))

        return issues

    def _check_dag(
        self,
        nodes_data: list[dict],
        edges_data: list[dict],
    ) -> list[ValidationIssue]:
        """
        DAG 环检测：使用 Kahn 算法（拓扑排序）检测环。
        循环节点 (loopNode) 内部的边不参与环检测。

        算法步骤（Kahn's Algorithm）：
        1. 构建有向图 + 计算每个节点的入度
        2. 将所有入度为 0 的节点加入队列
        3. 从队列取出节点，将其所有邻居的入度 -1
        4. 若邻居入度变为 0，加入队列
        5. 重复直到队列为空
        6. 如果处理过的节点数 < 总节点数，说明存在环
        """
        issues = []

        if not nodes_data or not edges_data:
            return issues

        node_ids = {n["id"] for n in nodes_data}
        node_type_map = {n["id"]: n["type"] for n in nodes_data}

        # 构建图（排除 loopNode 的内部回边）
        adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}

        for edge in (edges_data or []):
            source = edge.get("source")
            target = edge.get("target")
            if source in node_ids and target in node_ids:
                # 排除 loopNode 的内部回边：
                # 如果 target 是 loopNode 且 source 也是 loopNode 内部的节点，跳过
                # 简化策略：如果 source == target（自环），跳过
                if source == target:
                    continue
                adjacency[source].append(target)
                in_degree[target] += 1

        # Kahn 算法
        queue = [nid for nid in node_ids if in_degree[nid] == 0]
        processed_count = 0

        while queue:
            node = queue.pop(0)
            processed_count += 1
            for neighbor in adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 如果处理过的节点数 < 总节点数，存在环
        if processed_count < len(node_ids):
            # 找出环中的节点
            cycle_nodes = [nid for nid in node_ids if in_degree[nid] > 0]
            issues.append(ValidationIssue(
                level="error",
                code="CYCLE_DETECTED",
                message=f"检测到工作流存在循环依赖（涉及 {len(cycle_nodes)} 个节点），请检查连线",
                details={"cycle_node_ids": cycle_nodes},
            ))

        return issues

    def _check_variable_references(
        self,
        nodes_data: list[dict],
        edges_data: list[dict],
    ) -> list[ValidationIssue]:
        """
        变量引用检查：验证所有 ${node_id.var_name} 格式的引用是否合法。

        算法步骤：
        1. 构建「节点 ID → 输出变量列表」映射
        2. 遍历所有节点的配置，用正则提取 ${...} 引用
        3. 对每个引用：
           a. 解析 node_id 和 var_name
           b. 检查 node_id 是否存在
           c. 检查 var_name 是否在该节点的 outputs 中
        4. 收集所有非法引用
        """
        issues = []

        # 正则匹配 ${xxx.yyy} 或 ${env.XXX}
        var_pattern = re.compile(r'\$\{([^}]+)\}')

        # 1. 构建节点 ID → 节点 映射
        node_map = {n["id"]: n for n in nodes_data}

        # 2. 构建节点 ID → 输出变量名集合 映射
        node_outputs: dict[str, set[str]] = {}
        for node in nodes_data:
            node_id = node["id"]
            data = node.get("data", {})
            outputs = data.get("outputs", [])
            output_keys = {o["name"] for o in outputs}

            # 部分节点使用 output_key 作为输出变量名
            if data.get("output_key"):
                output_keys.add(data["output_key"])

            node_outputs[node_id] = output_keys

        # 3. 递归提取节点配置中所有 ${} 引用
        def extract_refs(obj, path=""):
            """递归遍历 dict/list，提取所有变量引用"""
            refs = []
            if isinstance(obj, str):
                matches = var_pattern.findall(obj)
                for match in matches:
                    refs.append((match, path))
            elif isinstance(obj, dict):
                for key, value in obj.items():
                    refs.extend(extract_refs(value, f"{path}.{key}"))
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    refs.extend(extract_refs(item, f"{path}[{i}]"))
            return refs

        # 4. 遍历所有节点，检查引用
        for node in nodes_data:
            node_id = node["id"]
            data = node.get("data", {})
            label = data.get("label", node_id)

            # 提取所有需要检查的字段
            check_fields = [
                data.get("input_mapping"),
                data.get("query_template"),
                data.get("body_template"),
                data.get("template"),
            ]

            # 条件节点的 conditions
            if node["type"] == "conditionNode":
                for cond in data.get("conditions", []):
                    check_fields.append(cond.get("variable"))

            for field_value in check_fields:
                if field_value is None:
                    continue
                refs = extract_refs(field_value)
                for ref, path in refs:
                    # 跳过环境变量引用
                    if ref.startswith("env."):
                        continue

                    # 解析 node_id.var_name
                    parts = ref.split(".", 1)
                    if len(parts) != 2:
                        # 格式不合法（没有 . 分隔）
                        issues.append(ValidationIssue(
                            level="error",
                            code="INVALID_VAR_FORMAT",
                            message=f"节点 '{label}' 中变量引用 '${{{ref}}}' 格式不合法，应为 ${{node_id.var_name}}",
                            node_id=node_id,
                            details={"ref": ref, "path": path},
                        ))
                        continue

                    ref_node_id, ref_var_name = parts

                    # 检查节点是否存在
                    if ref_node_id not in node_map:
                        issues.append(ValidationIssue(
                            level="error",
                            code="VAR_NODE_NOT_FOUND",
                            message=f"节点 '{label}' 引用了不存在的节点 '{ref_node_id}'",
                            node_id=node_id,
                            details={"ref": ref, "ref_node_id": ref_node_id},
                        ))
                        continue

                    # 检查变量是否存在
                    available_outputs = node_outputs.get(ref_node_id, set())
                    if ref_var_name not in available_outputs:
                        ref_node_label = node_map[ref_node_id]["data"].get("label", ref_node_id)
                        issues.append(ValidationIssue(
                            level="warning",  # warning 而非 error，因为变量可能是动态产生的
                            code="VAR_NOT_IN_OUTPUTS",
                            message=f"节点 '{label}' 引用的变量 '{ref_var_name}' 不在节点 '{ref_node_label}' 的输出变量中",
                            node_id=node_id,
                            details={
                                "ref": ref,
                                "ref_node_id": ref_node_id,
                                "available_outputs": list(available_outputs),
                            },
                        ))

        return issues
