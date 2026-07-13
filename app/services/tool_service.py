"""工具服务：处理工具 CRUD、Swagger 解析、工具测试调用"""

import time
import uuid
from typing import Optional

import httpx
from sqlalchemy import select, func, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.config import settings
from app.core.encryption import encrypt_value, decrypt_value
from app.core.tool_security import validate_tool_url, check_timeout
from app.models.tool import Tool
from app.models.agent_tool import AgentTool
from app.models.user import User


class ToolService:

    @staticmethod
    async def list_tools(
        db: AsyncSession,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        tool_type: Optional[str] = None,
    ) -> dict:
        """获取工具列表。"""
        base_condition = or_(Tool.is_preset == True, Tool.user_id == user_id)
        query = select(Tool).where(base_condition)

        if keyword:
            query = query.where(
                or_(
                    Tool.name.ilike(f"%{keyword}%"),
                    Tool.description.ilike(f"%{keyword}%"),
                )
            )

        if tool_type:
            query = query.where(Tool.tool_type == tool_type)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Tool.is_preset.desc(), Tool.name.asc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        tools = result.scalars().all()

        # 查询 agent 引用数量
        tool_ids = [t.id for t in tools]
        agent_counts = {}
        if tool_ids:
            count_result = await db.execute(
                select(AgentTool.tool_id, func.count(func.distinct(AgentTool.agent_id)))
                .where(AgentTool.tool_id.in_(tool_ids))
                .group_by(AgentTool.tool_id)
            )
            agent_counts = dict(count_result.all())

        items = [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "tool_type": t.tool_type,
                "is_preset": t.is_preset,
                "agent_count": agent_counts.get(t.id, 0),
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in tools
        ]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": page * page_size < total,
        }

    @staticmethod
    async def get_tool_detail(
        db: AsyncSession,
        tool_id: uuid.UUID,
        current_user: User,
    ) -> dict:
        """获取工具详情。"""
        result = await db.execute(select(Tool).where(Tool.id == tool_id))
        tool = result.scalar_one_or_none()

        if tool is None:
            raise AppException(code="TOOL_NOT_FOUND", message="工具不存在", status_code=404)

        if not tool.is_preset and tool.user_id != current_user.id:
            raise AppException(code="FORBIDDEN", message="无权查看此工具", status_code=403)

        # 查询引用数量
        count_result = await db.execute(
            select(func.count(func.distinct(AgentTool.agent_id)))
            .where(AgentTool.tool_id == tool_id)
        )
        agent_count = count_result.scalar() or 0

        # auth_config 脱敏
        auth_config_summary = None
        if tool.auth_type == "api_key" and tool.auth_config:
            auth_config_summary = {
                "type": "api_key",
                "header_name": tool.auth_config.get("header_name", ""),
                "has_value": bool(tool.auth_config.get("api_key_value_encrypted")),
            }
        elif tool.auth_type == "bearer" and tool.auth_config:
            auth_config_summary = {
                "type": "bearer",
                "has_value": bool(tool.auth_config.get("token_encrypted")),
            }

        return {
            "id": tool.id,
            "user_id": tool.user_id,
            "name": tool.name,
            "description": tool.description,
            "tool_type": tool.tool_type,
            "is_preset": tool.is_preset,
            "openapi_spec": tool.openapi_spec,
            "api_url": tool.api_url,
            "auth_type": tool.auth_type,
            "auth_config_summary": auth_config_summary,
            "agent_count": agent_count,
            "created_at": tool.created_at,
            "updated_at": tool.updated_at,
        }

    @staticmethod
    async def create_tool(
        db: AsyncSession,
        user_id: uuid.UUID,
        data: dict,
    ) -> Tool:
        """创建自定义工具。"""
        # 处理 auth_config 加密
        auth_config = data.pop("auth_config", None)
        auth_type = data.get("auth_type", "none")
        encrypted_auth_config = None

        if auth_config and auth_type != "none":
            encrypted_auth_config = ToolService._encrypt_auth_config(auth_type, auth_config)

        tool = Tool(
            user_id=user_id,
            tool_type="custom",
            is_preset=False,
            auth_config=encrypted_auth_config,
            **{k: v for k, v in data.items() if v is not None},
        )
        db.add(tool)
        await db.commit()
        await db.refresh(tool)
        return tool

    @staticmethod
    async def update_tool(
        db: AsyncSession,
        tool_id: uuid.UUID,
        current_user: User,
        data: dict,
    ) -> Tool:
        """更新自定义工具。"""
        result = await db.execute(select(Tool).where(Tool.id == tool_id))
        tool = result.scalar_one_or_none()

        if tool is None:
            raise AppException(code="TOOL_NOT_FOUND", message="工具不存在", status_code=404)

        if tool.is_preset:
            raise AppException(
                code="PRESET_TOOL_NOT_EDITABLE",
                message="预置工具不可修改",
                status_code=403,
            )

        if tool.user_id != current_user.id:
            raise AppException(code="FORBIDDEN", message="无权修改此工具", status_code=403)

        # 处理 auth_config
        auth_config = data.pop("auth_config", None)
        auth_type = data.get("auth_type", tool.auth_type)
        if auth_config is not None:
            if auth_type != "none":
                tool.auth_config = ToolService._encrypt_auth_config(auth_type, auth_config)
            else:
                tool.auth_config = None

        for key, value in data.items():
            if value is not None:
                setattr(tool, key, value)

        await db.commit()
        await db.refresh(tool)
        return tool

    @staticmethod
    async def delete_tool(
        db: AsyncSession,
        tool_id: uuid.UUID,
        current_user: User,
        force: bool = False,
    ) -> dict:
        """删除自定义工具。"""
        result = await db.execute(select(Tool).where(Tool.id == tool_id))
        tool = result.scalar_one_or_none()

        if tool is None:
            raise AppException(code="TOOL_NOT_FOUND", message="工具不存在", status_code=404)

        if tool.is_preset:
            raise AppException(
                code="PRESET_TOOL_NOT_DELETABLE",
                message="预置工具不可删除",
                status_code=403,
            )

        if tool.user_id != current_user.id:
            raise AppException(code="FORBIDDEN", message="无权删除此工具", status_code=403)

        # 查询引用数量
        count_result = await db.execute(
            select(func.count(func.distinct(AgentTool.agent_id)))
            .where(AgentTool.tool_id == tool_id)
        )
        agent_count = count_result.scalar() or 0

        if not force:
            return {
                "message": f"有 {agent_count} 个 Agent 正在使用此工具",
                "agent_count": agent_count,
                "deleted": False,
            }

        # 强制删除
        await db.execute(delete(AgentTool).where(AgentTool.tool_id == tool_id))
        db.delete(tool)
        await db.commit()

        return {
            "message": "工具已删除",
            "agent_count": agent_count,
            "deleted": True,
        }

    @staticmethod
    async def test_tool(
        db: AsyncSession,
        tool_id: uuid.UUID,
        current_user: User,
        parameters: dict,
        timeout: int = 30,
    ) -> dict:
        """测试调用工具。"""
        result = await db.execute(select(Tool).where(Tool.id == tool_id))
        tool = result.scalar_one_or_none()

        if tool is None:
            raise AppException(code="TOOL_NOT_FOUND", message="工具不存在", status_code=404)

        # 权限：预置工具或自己的工具
        if not tool.is_preset and tool.user_id != current_user.id:
            raise AppException(code="FORBIDDEN", message="无权测试此工具", status_code=403)

        # 获取 API URL（预置工具无 api_url，返回提示信息）
        if not tool.api_url:
            return {
                "success": False,
                "status_code": None,
                "response_body": None,
                "error_message": "预置工具不支持直接测试调用，请在 Agent 中使用",
                "duration_ms": None,
            }

        # 安全校验
        validate_tool_url(tool.api_url)
        check_timeout(timeout)

        # 构建请求头
        headers = {"Content-Type": "application/json"}
        if tool.auth_type == "api_key" and tool.auth_config:
            header_name = tool.auth_config.get("header_name", "X-API-Key")
            decrypted_key = decrypt_value(tool.auth_config.get("api_key_value_encrypted", ""))
            headers[header_name] = decrypted_key
        elif tool.auth_type == "bearer" and tool.auth_config:
            decrypted_token = decrypt_value(tool.auth_config.get("token_encrypted", ""))
            headers["Authorization"] = f"Bearer {decrypted_token}"

        # 发起 HTTP 请求
        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(verify=True) as client:
                response = await client.post(
                    tool.api_url,
                    json=parameters,
                    headers=headers,
                    timeout=timeout,
                )

            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            response_body = response.text

            # 截断过长的响应
            max_size = settings.tool_test_max_response_size
            if len(response_body) > max_size:
                response_body = response_body[:max_size] + "\n... [truncated]"

            return {
                "success": 200 <= response.status_code < 300,
                "status_code": response.status_code,
                "response_body": response_body,
                "error_message": None,
                "duration_ms": duration_ms,
            }

        except httpx.TimeoutException:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "success": False,
                "status_code": 408,
                "response_body": None,
                "error_message": f"请求超时（{timeout}秒）",
                "duration_ms": duration_ms,
            }
        except httpx.RequestError as e:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "success": False,
                "status_code": None,
                "response_body": None,
                "error_message": f"网络错误: {str(e)}",
                "duration_ms": duration_ms,
            }

    # ---- 内部方法 ----

    @staticmethod
    def _encrypt_auth_config(auth_type: str, auth_config: dict) -> dict:
        """加密 auth_config 中的敏感值。"""
        if auth_type == "api_key":
            api_key_value = auth_config.get("api_key_value")
            if not api_key_value:
                raise AppException(
                    code="INVALID_AUTH_CONFIG",
                    message="api_key 认证必须提供 api_key_value",
                    status_code=400,
                )
            return {
                "header_name": auth_config.get("header_name", "X-API-Key"),
                "api_key_value_encrypted": encrypt_value(api_key_value),
            }
        elif auth_type == "bearer":
            token = auth_config.get("token")
            if not token:
                raise AppException(
                    code="INVALID_AUTH_CONFIG",
                    message="bearer 认证必须提供 token",
                    status_code=400,
                )
            return {
                "token_encrypted": encrypt_value(token),
            }
        return None
