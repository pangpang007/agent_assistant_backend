"""Agent 服务：处理 Agent 的 CRUD、复制等操作"""

import uuid
from typing import Optional

from sqlalchemy import select, func, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.agent import Agent
from app.models.tool import Tool
from app.models.agent_tool import AgentTool
from app.models.agent_knowledge_base import AgentKnowledgeBase
from app.models.knowledge import KnowledgeBase
from app.models.model_provider import LLMModel, ModelProvider
from app.models.user import User


class AgentService:

    @staticmethod
    async def list_agents(
        db: AsyncSession,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        is_preset: Optional[bool] = None,
    ) -> dict:
        """
        获取 Agent 列表（预置 + 当前用户自定义）。
        """
        # 基础查询：预置 Agent + 当前用户的 Agent
        base_condition = or_(
            Agent.is_preset == True,
            Agent.user_id == user_id,
        )
        query = select(Agent).where(base_condition)

        # 搜索
        if keyword:
            query = query.where(
                or_(
                    Agent.name.ilike(f"%{keyword}%"),
                    Agent.description.ilike(f"%{keyword}%"),
                )
            )

        # 筛选
        if is_preset is not None:
            query = query.where(Agent.is_preset == is_preset)

        # 总数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页 + 排序
        query = query.order_by(Agent.is_preset.desc(), Agent.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        agents = result.scalars().all()

        # 查询每个 Agent 的工具数量
        agent_ids = [a.id for a in agents]
        tool_counts = {}
        if agent_ids:
            count_result = await db.execute(
                select(AgentTool.agent_id, func.count(AgentTool.id))
                .where(AgentTool.agent_id.in_(agent_ids))
                .group_by(AgentTool.agent_id)
            )
            tool_counts = dict(count_result.all())

        items = []
        for agent in agents:
            item = {
                "id": agent.id,
                "name": agent.name,
                "description": agent.description,
                "system_prompt": agent.system_prompt,
                "model_id": agent.model_id,
                "memory_strategy": agent.memory_strategy,
                "output_format": agent.output_format,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
                "is_preset": agent.is_preset,
                "tool_count": tool_counts.get(agent.id, 0),
                "created_at": agent.created_at,
                "updated_at": agent.updated_at,
            }
            items.append(item)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": page * page_size < total,
        }

    @staticmethod
    async def get_agent_detail(
        db: AsyncSession,
        agent_id: uuid.UUID,
        current_user: User,
    ) -> dict:
        """获取 Agent 详情，含工具列表和模型信息。"""
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()

        if agent is None:
            raise AppException(code="AGENT_NOT_FOUND", message="Agent 不存在", status_code=404)

        # 权限检查
        if not agent.is_preset and agent.user_id != current_user.id:
            raise AppException(code="FORBIDDEN", message="无权查看此 Agent", status_code=403)

        # 查询关联工具
        tool_result = await db.execute(
            select(Tool).join(AgentTool).where(AgentTool.agent_id == agent_id)
        )
        tools = tool_result.scalars().all()

        # 查询关联知识库
        kb_result = await db.execute(
            select(KnowledgeBase.id, KnowledgeBase.name)
            .join(AgentKnowledgeBase)
            .where(AgentKnowledgeBase.agent_id == agent_id)
        )
        knowledge_bases = [
            {"id": row[0], "name": row[1]} for row in kb_result.all()
        ]

        # 查询模型信息
        model_info = None
        if agent.model_id:
            model_result = await db.execute(
                select(LLMModel, ModelProvider)
                .join(ModelProvider, LLMModel.provider_id == ModelProvider.id)
                .where(LLMModel.id == agent.model_id)
            )
            row = model_result.one_or_none()
            if row:
                model, provider = row
                model_info = {
                    "id": str(model.id),
                    "model_name": model.model_name,
                    "display_name": model.display_name,
                    "provider_name": provider.provider_name,
                    "provider_type": provider.provider_type,
                }

        return {
            "id": agent.id,
            "user_id": agent.user_id,
            "name": agent.name,
            "description": agent.description,
            "system_prompt": agent.system_prompt,
            "model_id": agent.model_id,
            "model_info": model_info,
            "memory_strategy": agent.memory_strategy,
            "output_format": agent.output_format,
            "temperature": agent.temperature,
            "max_tokens": agent.max_tokens,
            "is_preset": agent.is_preset,
            "tools": [
                {
                    "id": t.id,
                    "name": t.name,
                    "description": t.description,
                    "tool_type": t.tool_type,
                }
                for t in tools
            ],
            "knowledge_base_ids": [kb["id"] for kb in knowledge_bases],
            "knowledge_bases": knowledge_bases,
            "created_at": agent.created_at,
            "updated_at": agent.updated_at,
        }

    @staticmethod
    async def create_agent(
        db: AsyncSession,
        user_id: uuid.UUID,
        data: dict,
    ) -> Agent:
        """创建自定义 Agent。"""
        # 校验 model_id
        if data.get("model_id"):
            await AgentService._validate_model(db, data["model_id"], user_id)

        # 校验 tool_ids
        tool_ids = data.pop("tool_ids", [])
        knowledge_base_ids = data.pop("knowledge_base_ids", [])
        if tool_ids:
            await AgentService._validate_tools(db, tool_ids, user_id)
        if knowledge_base_ids:
            await AgentService._validate_knowledge_bases(
                db, knowledge_base_ids, user_id
            )

        # 创建 Agent
        agent = Agent(
            user_id=user_id,
            is_preset=False,
            **{k: v for k, v in data.items() if v is not None},
        )
        db.add(agent)
        await db.flush()

        # 创建工具关联
        if tool_ids:
            for tool_id in tool_ids:
                db.add(AgentTool(agent_id=agent.id, tool_id=tool_id))

        if knowledge_base_ids:
            for kb_id in knowledge_base_ids:
                db.add(AgentKnowledgeBase(agent_id=agent.id, knowledge_base_id=kb_id))

        await db.commit()
        await db.refresh(agent)
        return agent

    @staticmethod
    async def update_agent(
        db: AsyncSession,
        agent_id: uuid.UUID,
        current_user: User,
        data: dict,
    ) -> Agent:
        """更新自定义 Agent。"""
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()

        if agent is None:
            raise AppException(code="AGENT_NOT_FOUND", message="Agent 不存在", status_code=404)

        if agent.is_preset:
            raise AppException(
                code="PRESET_AGENT_READONLY",
                message="预置 Agent 不可修改",
                status_code=403,
            )

        if agent.user_id != current_user.id:
            raise AppException(code="FORBIDDEN", message="无权修改此 Agent", status_code=403)

        # 处理 tool_ids（特殊逻辑）
        tool_ids = data.pop("tool_ids", None)
        knowledge_base_ids = data.pop("knowledge_base_ids", None)
        if tool_ids is not None:
            if tool_ids:
                await AgentService._validate_tools(db, tool_ids, current_user.id)
        if knowledge_base_ids is not None:
            if knowledge_base_ids:
                await AgentService._validate_knowledge_bases(
                    db, knowledge_base_ids, current_user.id
                )

        # 校验 model_id
        if data.get("model_id"):
            await AgentService._validate_model(db, data["model_id"], current_user.id)

        # 更新字段
        for key, value in data.items():
            if value is not None:
                setattr(agent, key, value)

        # 更新工具关联
        if tool_ids is not None:
            await db.execute(
                delete(AgentTool).where(AgentTool.agent_id == agent_id)
            )
            for tool_id in tool_ids:
                db.add(AgentTool(agent_id=agent.id, tool_id=tool_id))

        if knowledge_base_ids is not None:
            await db.execute(
                delete(AgentKnowledgeBase).where(
                    AgentKnowledgeBase.agent_id == agent_id
                )
            )
            for kb_id in knowledge_base_ids:
                db.add(
                    AgentKnowledgeBase(agent_id=agent.id, knowledge_base_id=kb_id)
                )

        await db.commit()
        await db.refresh(agent)
        return agent

    @staticmethod
    async def delete_agent(
        db: AsyncSession,
        agent_id: uuid.UUID,
        current_user: User,
    ) -> None:
        """删除自定义 Agent。"""
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()

        if agent is None:
            raise AppException(code="AGENT_NOT_FOUND", message="Agent 不存在", status_code=404)

        if agent.is_preset:
            raise AppException(
                code="PRESET_AGENT_NOT_DELETABLE",
                message="预置 Agent 不可删除",
                status_code=403,
            )

        if agent.user_id != current_user.id:
            raise AppException(code="FORBIDDEN", message="无权删除此 Agent", status_code=403)

        db.delete(agent)
        await db.commit()

    @staticmethod
    async def copy_agent(
        db: AsyncSession,
        agent_id: uuid.UUID,
        current_user: User,
        new_name: Optional[str] = None,
    ) -> Agent:
        """复制预置 Agent 为自定义 Agent。"""
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()

        if agent is None:
            raise AppException(code="AGENT_NOT_FOUND", message="Agent 不存在", status_code=404)

        if not agent.is_preset:
            raise AppException(
                code="ONLY_PRESET_CAN_COPY",
                message="仅预置 Agent 可复制",
                status_code=400,
            )

        # 查询源 Agent 的工具关联
        tool_result = await db.execute(
            select(AgentTool.tool_id).where(AgentTool.agent_id == agent.id)
        )
        tool_ids = [row[0] for row in tool_result.all()]

        # 创建新 Agent
        new_agent = Agent(
            user_id=current_user.id,
            name=new_name or f"{agent.name} - 副本",
            description=agent.description,
            system_prompt=agent.system_prompt,
            model_id=agent.model_id,
            memory_strategy=agent.memory_strategy,
            output_format=agent.output_format,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
            is_preset=False,
        )
        db.add(new_agent)
        await db.flush()

        # 复制工具关联
        for tool_id in tool_ids:
            db.add(AgentTool(agent_id=new_agent.id, tool_id=tool_id))

        await db.commit()
        await db.refresh(new_agent)
        return new_agent

    # ---- 内部校验方法 ----

    @staticmethod
    async def _validate_model(
        db: AsyncSession, model_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """校验模型是否存在且可用。"""
        result = await db.execute(
            select(LLMModel, ModelProvider)
            .join(ModelProvider, LLMModel.provider_id == ModelProvider.id)
            .where(
                and_(
                    LLMModel.id == model_id,
                    LLMModel.is_enabled == True,
                    ModelProvider.user_id == user_id,
                    ModelProvider.is_enabled == True,
                )
            )
        )
        if result.one_or_none() is None:
            raise AppException(
                code="INVALID_MODEL_ID",
                message="指定的模型不存在或未启用",
                status_code=400,
            )

    @staticmethod
    async def _validate_tools(
        db: AsyncSession, tool_ids: list[uuid.UUID], user_id: uuid.UUID
    ) -> None:
        """校验工具 ID 是否有效（预置工具或自己的工具）。"""
        result = await db.execute(
            select(Tool.id).where(
                and_(
                    Tool.id.in_(tool_ids),
                    or_(Tool.is_preset == True, Tool.user_id == user_id),
                )
            )
        )
        valid_ids = set(row[0] for row in result.all())
        invalid_ids = set(tool_ids) - valid_ids
        if invalid_ids:
            raise AppException(
                code="INVALID_TOOL_IDS",
                message="部分工具 ID 无效",
                status_code=400,
                details=[{"tool_id": str(tid), "reason": "不存在或无权使用"} for tid in invalid_ids],
            )

    @staticmethod
    async def _validate_knowledge_bases(
        db: AsyncSession, kb_ids: list[uuid.UUID], user_id: uuid.UUID
    ) -> None:
        """校验知识库 ID 是否属于当前用户。"""
        result = await db.execute(
            select(KnowledgeBase.id).where(
                and_(KnowledgeBase.id.in_(kb_ids), KnowledgeBase.user_id == user_id)
            )
        )
        valid_ids = set(row[0] for row in result.all())
        invalid_ids = set(kb_ids) - valid_ids
        if invalid_ids:
            raise AppException(
                code="INVALID_KNOWLEDGE_BASE_IDS",
                message="部分知识库 ID 无效",
                status_code=400,
                details=[
                    {"knowledge_base_id": str(kid), "reason": "不存在或无权使用"}
                    for kid in invalid_ids
                ],
            )
