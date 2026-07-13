
import uuid
import structlog
from uuid import UUID
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import VersionNotFoundError
from app.models.workflow import Workflow, WorkflowVersion
from app.schemas.workflow import VersionDiffResponse, WorkflowVersionResponse

logger = structlog.get_logger()


class VersionService:
    """版本管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_version(
        self,
        workflow_id: UUID,
        version_number: int,
        nodes_data: Optional[list],
        edges_data: Optional[list],
        tag: Optional[str] = None,
    ) -> WorkflowVersion:
        """
        创建新版本。在每次工作流保存时调用。
        
        Args:
            workflow_id: 工作流 ID
            version_number: 版本号（由调用方计算）
            nodes_data: 当前节点数据快照
            edges_data: 当前边数据快照
            tag: 可选标签
        
        Returns:
            新创建的 WorkflowVersion 记录
        """
        version = WorkflowVersion(
            id=uuid.uuid4(),
            workflow_id=workflow_id,
            version_number=version_number,
            tag=tag,
            nodes_data=nodes_data,
            edges_data=edges_data,
        )
        self.db.add(version)
        await self.db.flush()
        logger.info("version_created", workflow_id=str(workflow_id), version=version_number)
        return version

    async def list_versions(
        self,
        workflow_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """
        获取版本列表，按版本号倒序。
        """
        # 查询总数
        count_result = await self.db.execute(
            select(func.count(WorkflowVersion.id)).where(
                WorkflowVersion.workflow_id == workflow_id
            )
        )
        total = count_result.scalar()

        # 分页查询
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == workflow_id)
            .order_by(WorkflowVersion.version_number.desc())
            .offset(offset)
            .limit(page_size)
        )
        versions = result.scalars().all()

        items = []
        for v in versions:
            items.append(WorkflowVersionResponse(
                id=v.id,
                workflow_id=v.workflow_id,
                version_number=v.version_number,
                tag=v.tag,
                node_count=len(v.nodes_data) if v.nodes_data else 0,
                created_at=v.created_at,
            ))

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": offset + page_size < total,
        }

    async def get_version(
        self,
        workflow_id: UUID,
        version_number: int,
    ) -> Optional[WorkflowVersion]:
        """
        获取指定版本详情。
        """
        result = await self.db.execute(
            select(WorkflowVersion).where(
                WorkflowVersion.workflow_id == workflow_id,
                WorkflowVersion.version_number == version_number,
            )
        )
        return result.scalar_one_or_none()

    async def rollback_to_version(
        self,
        workflow: Workflow,
        version_number: int,
    ) -> dict:
        """
        回滚到指定版本。
        
        逻辑：
        1. 查询目标版本
        2. 将目标版本的 nodes_data/edges_data 复制到工作流
        3. current_version += 1
        4. 创建新版本（tag = "回滚自 vX"）
        """
        # 查询目标版本
        target = await self.get_version(workflow.id, version_number)
        if not target:
            raise VersionNotFoundError(version_number)

        # 更新工作流数据
        new_version_number = workflow.current_version + 1
        workflow.nodes_data = target.nodes_data
        workflow.edges_data = target.edges_data
        workflow.current_version = new_version_number

        # 创建新版本
        new_version = await self.create_version(
            workflow_id=workflow.id,
            version_number=new_version_number,
            nodes_data=target.nodes_data,
            edges_data=target.edges_data,
            tag=f"回滚自 v{version_number}",
        )

        await self.db.flush()
        logger.info(
            "version_rollback",
            workflow_id=str(workflow.id),
            from_version=version_number,
            to_version=new_version_number,
        )

        return {
            "message": f"已回滚到版本 {version_number}",
            "workflow_id": workflow.id,
            "version_number": version_number,
            "new_version_number": new_version_number,
        }

    async def diff_versions(
        self,
        workflow_id: UUID,
        v1: int,
        v2: int,
    ) -> VersionDiffResponse:
        """
        对比两个版本的差异。
        
        使用基于节点 ID 的 diff 算法：
        1. 构建 v1 和 v2 的节点 ID 集合
        2. added = v2 有但 v1 没有的节点
        3. removed = v1 有但 v2 没有的节点
        4. common = 两者都有的节点，逐个对比 data 字段
        5. 边同理（基于 source+target 对进行匹配）
        """
        version1 = await self.get_version(workflow_id, v1)
        version2 = await self.get_version(workflow_id, v2)

        if not version1 or not version2:
            raise VersionNotFoundError(v1 if not version1 else v2)

        nodes_v1 = {n["id"]: n for n in (version1.nodes_data or [])}
        nodes_v2 = {n["id"]: n for n in (version2.nodes_data or [])}

        ids_v1 = set(nodes_v1.keys())
        ids_v2 = set(nodes_v2.keys())

        # 节点 diff
        added_nodes = [nodes_v2[nid] for nid in (ids_v2 - ids_v1)]
        removed_nodes = [nodes_v1[nid] for nid in (ids_v1 - ids_v2)]
        modified_nodes = []

        for nid in (ids_v1 & ids_v2):
            n1 = nodes_v1[nid]
            n2 = nodes_v2[nid]
            if n1 != n2:
                # 找出具体修改了哪些字段
                changes = {}
                all_keys = set(list(n1.keys()) + list(n2.keys()))
                for key in all_keys:
                    if n1.get(key) != n2.get(key):
                        changes[key] = {"old": n1.get(key), "new": n2.get(key)}
                modified_nodes.append({
                    "id": nid,
                    "type": n2.get("type", n1.get("type")),
                    "label": n2.get("data", {}).get("label", ""),
                    "changes": changes,
                })

        # 边 diff（基于 source+target 对匹配）
        def edge_key(edge):
            return f"{edge.get('source')}->{edge.get('target')}:{edge.get('sourceHandle', '')}"

        edges_v1 = {edge_key(e): e for e in (version1.edges_data or [])}
        edges_v2 = {edge_key(e): e for e in (version2.edges_data or [])}

        eids_v1 = set(edges_v1.keys())
        eids_v2 = set(edges_v2.keys())

        added_edges = [edges_v2[eid] for eid in (eids_v2 - eids_v1)]
        removed_edges = [edges_v1[eid] for eid in (eids_v1 - eids_v2)]
        modified_edges = []

        for eid in (eids_v1 & eids_v2):
            e1 = edges_v1[eid]
            e2 = edges_v2[eid]
            if e1 != e2:
                modified_edges.append({
                    "id": eid,
                    "old": e1,
                    "new": e2,
                })

        return VersionDiffResponse(
            v1=v1,
            v2=v2,
            added_nodes=added_nodes,
            removed_nodes=removed_nodes,
            modified_nodes=modified_nodes,
            added_edges=added_edges,
            removed_edges=removed_edges,
            modified_edges=modified_edges,
        )
