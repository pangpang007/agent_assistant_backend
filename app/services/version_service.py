import uuid
from typing import Any, Optional
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ForbiddenException,
    NoTagToRemoveError,
    VersionNotFoundError,
    WorkflowNotFoundError,
)
from app.models.workflow import Workflow, WorkflowVersion
from app.schemas.workflow import VersionDiffResponse, WorkflowVersionResponse

logger = structlog.get_logger()


def deep_diff(old: dict, new: dict, prefix: str = "") -> list[dict[str, Any]]:
    """递归对比两个字典的差异，返回变更列表。"""
    changes: list[dict[str, Any]] = []
    all_keys = set(list(old.keys()) + list(new.keys()))

    for key in all_keys:
        field_path = f"{prefix}.{key}" if prefix else key
        old_val = old.get(key)
        new_val = new.get(key)

        if key not in old:
            changes.append(
                {
                    "field": field_path,
                    "old_value": None,
                    "new_value": new_val,
                    "change_type": "added",
                }
            )
        elif key not in new:
            changes.append(
                {
                    "field": field_path,
                    "old_value": old_val,
                    "new_value": None,
                    "change_type": "removed",
                }
            )
        elif isinstance(old_val, dict) and isinstance(new_val, dict):
            changes.extend(deep_diff(old_val, new_val, field_path))
        elif isinstance(old_val, list) and isinstance(new_val, list):
            if old_val != new_val:
                changes.append(
                    {
                        "field": field_path,
                        "old_value": old_val,
                        "new_value": new_val,
                        "change_type": "modified",
                    }
                )
        elif old_val != new_val:
            changes.append(
                {
                    "field": field_path,
                    "old_value": old_val,
                    "new_value": new_val,
                    "change_type": "modified",
                }
            )

    return changes


def diff_nodes(v1_nodes: Optional[list], v2_nodes: Optional[list]) -> dict:
    v1_map = {n["id"]: n for n in (v1_nodes or [])}
    v2_map = {n["id"]: n for n in (v2_nodes or [])}

    v1_ids = set(v1_map.keys())
    v2_ids = set(v2_map.keys())

    added = [
        {
            "id": nid,
            "type": v2_map[nid].get("type", "unknown"),
            "label": v2_map[nid].get("data", {}).get("label", ""),
            "position": v2_map[nid].get("position", {}),
        }
        for nid in (v2_ids - v1_ids)
    ]

    removed = [
        {
            "id": nid,
            "type": v1_map[nid].get("type", "unknown"),
            "label": v1_map[nid].get("data", {}).get("label", ""),
        }
        for nid in (v1_ids - v2_ids)
    ]

    modified = []
    for nid in v1_ids & v2_ids:
        n1 = v1_map[nid]
        n2 = v2_map[nid]
        changes = deep_diff(n1.get("data", {}) or {}, n2.get("data", {}) or {})
        if changes:
            modified.append(
                {
                    "id": nid,
                    "type": n1.get("type", "unknown"),
                    "label": n2.get("data", {}).get(
                        "label", n1.get("data", {}).get("label", "")
                    ),
                    "changes": changes,
                }
            )

    return {"added": added, "removed": removed, "modified": modified}


def diff_edges(v1_edges: Optional[list], v2_edges: Optional[list]) -> dict:
    def edge_key(edge: dict) -> tuple:
        return (
            edge.get("source", ""),
            edge.get("target", ""),
            edge.get("sourceHandle", ""),
        )

    v1_map = {edge_key(e): e for e in (v1_edges or [])}
    v2_map = {edge_key(e): e for e in (v2_edges or [])}

    v1_keys = set(v1_map.keys())
    v2_keys = set(v2_map.keys())

    added = [
        {
            "id": v2_map[k].get("id", ""),
            "source": k[0],
            "target": k[1],
            "source_handle": k[2],
        }
        for k in (v2_keys - v1_keys)
    ]

    removed = [
        {
            "id": v1_map[k].get("id", ""),
            "source": k[0],
            "target": k[1],
            "source_handle": k[2],
        }
        for k in (v1_keys - v2_keys)
    ]

    modified = []
    for k in v1_keys & v2_keys:
        e1 = v1_map[k]
        e2 = v2_map[k]
        if e1.get("type") != e2.get("type") or e1.get("data") != e2.get("data"):
            modified.append(
                {
                    "id": e1.get("id", ""),
                    "source": k[0],
                    "old_target": k[1],
                    "new_target": k[1],
                    "changes": deep_diff(
                        {key: e1[key] for key in ["type", "data", "label"] if key in e1},
                        {key: e2[key] for key in ["type", "data", "label"] if key in e2},
                    ),
                }
            )

    return {"added": added, "removed": removed, "modified": modified}


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
        count_result = await self.db.execute(
            select(func.count(WorkflowVersion.id)).where(
                WorkflowVersion.workflow_id == workflow_id
            )
        )
        total = count_result.scalar()

        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == workflow_id)
            .order_by(WorkflowVersion.version_number.desc())
            .offset(offset)
            .limit(page_size)
        )
        versions = result.scalars().all()

        items = [
            WorkflowVersionResponse(
                id=v.id,
                workflow_id=v.workflow_id,
                version_number=v.version_number,
                tag=v.tag,
                node_count=len(v.nodes_data) if v.nodes_data else 0,
                created_at=v.created_at,
            )
            for v in versions
        ]

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
        target = await self.get_version(workflow.id, version_number)
        if not target:
            raise VersionNotFoundError(version_number)

        new_version_number = workflow.current_version + 1
        workflow.nodes_data = target.nodes_data
        workflow.edges_data = target.edges_data
        workflow.current_version = new_version_number

        await self.create_version(
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

    async def tag_version(
        self,
        workflow_id: UUID,
        version_number: int,
        tag: str,
        user_id: UUID,
    ) -> dict:
        await self._get_workflow_with_auth(workflow_id, user_id)
        version = await self._get_version(workflow_id, version_number)
        if not version:
            raise VersionNotFoundError(version_number)

        version.tag = tag
        await self.db.flush()

        return {
            "id": version.id,
            "workflow_id": version.workflow_id,
            "version_number": version.version_number,
            "tag": version.tag,
            "node_count": len(version.nodes_data) if version.nodes_data else 0,
            "created_at": version.created_at,
        }

    async def remove_tag(
        self,
        workflow_id: UUID,
        version_number: int,
        user_id: UUID,
    ) -> dict:
        await self._get_workflow_with_auth(workflow_id, user_id)
        version = await self._get_version(workflow_id, version_number)
        if not version:
            raise VersionNotFoundError(version_number)
        if version.tag is None:
            raise NoTagToRemoveError()

        version.tag = None
        await self.db.flush()

        return {
            "id": version.id,
            "workflow_id": version.workflow_id,
            "version_number": version.version_number,
            "tag": version.tag,
            "node_count": len(version.nodes_data) if version.nodes_data else 0,
            "created_at": version.created_at,
        }

    async def diff_versions(
        self,
        workflow_id: UUID,
        v1: int,
        v2: int,
        user_id: Optional[UUID] = None,
    ) -> VersionDiffResponse:
        if user_id is not None:
            await self._get_workflow_with_auth(workflow_id, user_id)

        version1 = await self.get_version(workflow_id, v1)
        version2 = await self.get_version(workflow_id, v2)

        if not version1:
            raise VersionNotFoundError(v1)
        if not version2:
            raise VersionNotFoundError(v2)

        node_diff = diff_nodes(version1.nodes_data, version2.nodes_data)
        edge_diff = diff_edges(version1.edges_data, version2.edges_data)

        return VersionDiffResponse(
            v1=v1,
            v2=v2,
            added_nodes=node_diff["added"],
            removed_nodes=node_diff["removed"],
            modified_nodes=node_diff["modified"],
            added_edges=edge_diff["added"],
            removed_edges=edge_diff["removed"],
            modified_edges=edge_diff["modified"],
        )

    async def _get_workflow_with_auth(
        self, workflow_id: UUID, user_id: UUID
    ) -> Workflow:
        result = await self.db.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise WorkflowNotFoundError()
        if workflow.user_id != user_id:
            raise ForbiddenException("无权操作此工作流")
        return workflow

    async def _get_version(
        self, workflow_id: UUID, version_number: int
    ) -> Optional[WorkflowVersion]:
        return await self.get_version(workflow_id, version_number)
