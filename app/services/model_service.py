"""模型管理服务：供应商 CRUD、模型配置、API Key 加密/脱敏、用量统计"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.encryption import encrypt_value, decrypt_value, mask_api_key
from app.models.model_provider import ModelProvider, LLMModel, ModelUsage
from app.models.agent import Agent
from app.models.user import User


# 常见模型预定义价格（每百万 token，USD）
PRESET_MODEL_PRICES = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
}


class ModelService:

    @staticmethod
    async def list_providers(
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[dict]:
        """获取供应商列表。"""
        result = await db.execute(
            select(ModelProvider)
            .where(ModelProvider.user_id == user_id)
            .order_by(ModelProvider.created_at.desc())
        )
        providers = result.scalars().all()

        items = []
        for p in providers:
            # 查模型数量
            model_count_result = await db.execute(
                select(func.count(LLMModel.id)).where(LLMModel.provider_id == p.id)
            )
            model_count = model_count_result.scalar() or 0

            enabled_model_count_result = await db.execute(
                select(func.count(LLMModel.id)).where(
                    and_(LLMModel.provider_id == p.id, LLMModel.is_enabled == True)
                )
            )
            enabled_model_count = enabled_model_count_result.scalar() or 0

            has_default_result = await db.execute(
                select(func.count(LLMModel.id)).where(
                    and_(LLMModel.provider_id == p.id, LLMModel.is_default == True)
                )
            )
            has_default = (has_default_result.scalar() or 0) > 0

            # 解密 API Key 后脱敏
            decrypted_key = decrypt_value(p.api_key_encrypted)
            masked_key = mask_api_key(decrypted_key)

            items.append({
                "id": p.id,
                "provider_name": p.provider_name,
                "provider_type": p.provider_type,
                "base_url": p.base_url,
                "api_key_masked": masked_key,
                "is_enabled": p.is_enabled,
                "model_count": model_count,
                "enabled_model_count": enabled_model_count,
                "has_default_model": has_default,
                "created_at": p.created_at,
            })

        return items

    @staticmethod
    async def create_provider(
        db: AsyncSession,
        user_id: uuid.UUID,
        data: dict,
    ) -> ModelProvider:
        """添加供应商。"""
        # 加密 API Key
        api_key_plain = data.pop("api_key")
        model_names = data.pop("models", [])
        api_key_encrypted = encrypt_value(api_key_plain)

        # 默认 base_url
        provider_type = data.get("provider_type")
        base_url = data.get("base_url")
        if not base_url:
            default_urls = {
                "openai": "https://api.openai.com/v1",
                "anthropic": "https://api.anthropic.com",
                "google": "https://generativelanguage.googleapis.com/v1beta",
            }
            base_url = default_urls.get(provider_type)

        provider = ModelProvider(
            user_id=user_id,
            api_key_encrypted=api_key_encrypted,
            base_url=base_url,
            is_enabled=True,
            **{k: v for k, v in data.items() if v is not None},
        )
        db.add(provider)
        await db.flush()

        # 创建初始模型
        for model_name in model_names:
            prices = PRESET_MODEL_PRICES.get(model_name, {"input": 0, "output": 0})
            model = LLMModel(
                provider_id=provider.id,
                model_name=model_name,
                display_name=model_name,
                input_price=Decimal(str(prices["input"])),
                output_price=Decimal(str(prices["output"])),
                is_enabled=True,
            )
            db.add(model)

        await db.flush()
        await db.refresh(provider)
        return provider

    @staticmethod
    async def update_provider(
        db: AsyncSession,
        provider_id: uuid.UUID,
        current_user: User,
        data: dict,
    ) -> ModelProvider:
        """更新供应商。"""
        provider = await ModelService._get_provider_with_permission(db, provider_id, current_user.id)

        if data.get("api_key"):
            provider.api_key_encrypted = encrypt_value(data.pop("api_key"))

        for key, value in data.items():
            if value is not None:
                setattr(provider, key, value)

        await db.commit()
        await db.refresh(provider)
        return provider

    @staticmethod
    async def delete_provider(
        db: AsyncSession,
        provider_id: uuid.UUID,
        current_user: User,
    ) -> dict:
        """删除供应商。"""
        provider = await ModelService._get_provider_with_permission(db, provider_id, current_user.id)

        # 检查是否有 Agent 正在使用
        model_ids_result = await db.execute(
            select(LLMModel.id).where(LLMModel.provider_id == provider_id)
        )
        model_ids = [row[0] for row in model_ids_result.all()]

        if model_ids:
            agent_count_result = await db.execute(
                select(func.count(Agent.id)).where(Agent.model_id.in_(model_ids))
            )
            agent_count = agent_count_result.scalar() or 0
            if agent_count > 0:
                raise AppException(
                    code="PROVIDER_IN_USE",
                    message=f"有 {agent_count} 个 Agent 正在使用此供应商下的模型",
                    status_code=400,
                )

        affected_models = len(model_ids)
        db.delete(provider)  # cascade 自动删除 models
        await db.commit()

        return {
            "message": "供应商已删除",
            "provider_id": provider_id,
            "affected_models": affected_models,
        }

    @staticmethod
    async def toggle_provider(
        db: AsyncSession,
        provider_id: uuid.UUID,
        current_user: User,
    ) -> dict:
        """切换供应商启用/禁用。"""
        provider = await ModelService._get_provider_with_permission(db, provider_id, current_user.id)

        provider.is_enabled = not provider.is_enabled

        # 禁用时同时禁用所有模型
        if not provider.is_enabled:
            await db.execute(
                update(LLMModel)
                .where(LLMModel.provider_id == provider_id)
                .values(is_enabled=False)
            )

        await db.commit()
        await db.refresh(provider)

        status_text = "已启用" if provider.is_enabled else "已禁用"
        return {
            "id": provider.id,
            "provider_name": provider.provider_name,
            "is_enabled": provider.is_enabled,
            "message": f"供应商{status_text}",
        }

    @staticmethod
    async def list_models(
        db: AsyncSession,
        provider_id: uuid.UUID,
        current_user: User,
    ) -> dict:
        """获取供应商下的模型列表。"""
        provider = await ModelService._get_provider_with_permission(db, provider_id, current_user.id)

        result = await db.execute(
            select(LLMModel)
            .where(LLMModel.provider_id == provider_id)
            .order_by(LLMModel.is_default.desc(), LLMModel.is_enabled.desc(), LLMModel.model_name.asc())
        )
        models = result.scalars().all()

        return {
            "items": [
                {
                    "id": m.id,
                    "provider_id": m.provider_id,
                    "model_name": m.model_name,
                    "display_name": m.display_name,
                    "input_price": float(m.input_price),
                    "output_price": float(m.output_price),
                    "is_enabled": m.is_enabled,
                    "is_default": m.is_default,
                    "created_at": m.created_at,
                }
                for m in models
            ],
            "provider_name": provider.provider_name,
            "provider_type": provider.provider_type,
        }

    @staticmethod
    async def create_model(
        db: AsyncSession,
        provider_id: uuid.UUID,
        current_user: User,
        data: dict,
    ) -> LLMModel:
        """在供应商下添加模型。"""
        provider = await ModelService._get_provider_with_permission(db, provider_id, current_user.id)

        # 检查是否已存在
        existing = await db.execute(
            select(LLMModel).where(
                and_(
                    LLMModel.provider_id == provider_id,
                    LLMModel.model_name == data["model_name"],
                )
            )
        )
        existing_model = existing.scalar_one_or_none()

        if existing_model:
            if existing_model.is_enabled:
                raise AppException(
                    code="MODEL_ALREADY_EXISTS",
                    message="该模型已存在且已启用",
                    status_code=409,
                )
            else:
                # 重新启用
                existing_model.is_enabled = True
                for key, value in data.items():
                    if value is not None:
                        setattr(existing_model, key, value)
                await db.commit()
                await db.refresh(existing_model)
                return existing_model

        model = LLMModel(
            provider_id=provider_id,
            **{k: v for k, v in data.items() if v is not None},
            is_enabled=True,
        )
        db.add(model)
        await db.commit()
        await db.refresh(model)
        return model

    @staticmethod
    async def update_model(
        db: AsyncSession,
        model_id: uuid.UUID,
        current_user: User,
        data: dict,
    ) -> LLMModel:
        """更新模型配置。"""
        result = await db.execute(
            select(LLMModel)
            .join(ModelProvider, LLMModel.provider_id == ModelProvider.id)
            .where(
                and_(LLMModel.id == model_id, ModelProvider.user_id == current_user.id)
            )
        )
        model = result.scalar_one_or_none()

        if model is None:
            raise AppException(code="MODEL_NOT_FOUND", message="模型不存在", status_code=404)

        for key, value in data.items():
            if value is not None:
                setattr(model, key, value)

        # 若禁用且是默认，取消默认
        if data.get("is_enabled") == False and model.is_default:
            model.is_default = False

        await db.commit()
        await db.refresh(model)
        return model

    @staticmethod
    async def delete_model(
        db: AsyncSession,
        model_id: uuid.UUID,
        current_user: User,
    ) -> None:
        """删除模型。"""
        result = await db.execute(
            select(LLMModel)
            .join(ModelProvider, LLMModel.provider_id == ModelProvider.id)
            .where(
                and_(LLMModel.id == model_id, ModelProvider.user_id == current_user.id)
            )
        )
        model = result.scalar_one_or_none()

        if model is None:
            raise AppException(code="MODEL_NOT_FOUND", message="模型不存在", status_code=404)

        # 检查是否有 Agent 使用
        agent_count_result = await db.execute(
            select(func.count(Agent.id)).where(Agent.model_id == model_id)
        )
        if (agent_count_result.scalar() or 0) > 0:
            raise AppException(
                code="MODEL_IN_USE",
                message="该模型正在被 Agent 使用，无法删除",
                status_code=400,
            )

        db.delete(model)
        await db.commit()

    @staticmethod
    async def set_default_model(
        db: AsyncSession,
        model_id: uuid.UUID,
        current_user: User,
    ) -> LLMModel:
        """设为默认模型。"""
        # 获取模型（带权限检查）
        result = await db.execute(
            select(LLMModel)
            .join(ModelProvider, LLMModel.provider_id == ModelProvider.id)
            .where(
                and_(
                    LLMModel.id == model_id,
                    ModelProvider.user_id == current_user.id,
                    LLMModel.is_enabled == True,
                    ModelProvider.is_enabled == True,
                )
            )
        )
        model = result.scalar_one_or_none()

        if model is None:
            raise AppException(code="MODEL_NOT_FOUND", message="模型不存在或未启用", status_code=404)

        # 清除该用户所有模型的默认标记
        provider_ids_result = await db.execute(
            select(ModelProvider.id).where(ModelProvider.user_id == current_user.id)
        )
        provider_ids = [row[0] for row in provider_ids_result.all()]

        await db.execute(
            update(LLMModel)
            .where(LLMModel.provider_id.in_(provider_ids))
            .values(is_default=False)
        )

        # 设为默认
        model.is_default = True
        await db.commit()
        await db.refresh(model)
        return model

    @staticmethod
    async def get_usage(
        db: AsyncSession,
        user_id: uuid.UUID,
        group_by: str = "day",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        provider_id: Optional[uuid.UUID] = None,
        model_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """用量统计。"""
        # 默认最近 30 天
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # 基础查询
        query = select(ModelUsage).where(
            and_(
                ModelUsage.user_id == user_id,
                ModelUsage.date >= start_date,
                ModelUsage.date <= end_date,
            )
        )

        if provider_id:
            query = query.where(ModelUsage.provider_id == provider_id)
        if model_id:
            query = query.where(ModelUsage.model_id == model_id)

        # 聚合
        if group_by == "day":
            group_col = ModelUsage.date
        elif group_by == "model":
            group_col = ModelUsage.model_name
        elif group_by == "provider":
            group_col = ModelUsage.provider_name
        else:
            group_col = ModelUsage.date

        agg_query = (
            select(
                group_col.label("group_key"),
                func.sum(ModelUsage.input_tokens).label("input_tokens"),
                func.sum(ModelUsage.output_tokens).label("output_tokens"),
                func.sum(ModelUsage.cost).label("cost"),
            )
            .where(
                and_(
                    ModelUsage.user_id == user_id,
                    ModelUsage.date >= start_date,
                    ModelUsage.date <= end_date,
                )
            )
            .group_by(group_col)
            .order_by(group_col)
        )

        if provider_id:
            agg_query = agg_query.where(ModelUsage.provider_id == provider_id)
        if model_id:
            agg_query = agg_query.where(ModelUsage.model_id == model_id)

        result = await db.execute(agg_query)
        rows = result.all()

        items = [
            {
                "group_key": str(row.group_key),
                "input_tokens": row.input_tokens or 0,
                "output_tokens": row.output_tokens or 0,
                "total_tokens": (row.input_tokens or 0) + (row.output_tokens or 0),
                "cost": float(row.cost or 0),
            }
            for row in rows
        ]

        # 汇总
        summary = {
            "total_input_tokens": sum(i["input_tokens"] for i in items),
            "total_output_tokens": sum(i["output_tokens"] for i in items),
            "total_tokens": sum(i["total_tokens"] for i in items),
            "total_cost": sum(i["cost"] for i in items),
            "date_range": f"{start_date} ~ {end_date}",
        }

        return {"items": items, "summary": summary}

    # ---- 内部方法 ----

    @staticmethod
    async def _get_provider_with_permission(
        db: AsyncSession,
        provider_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ModelProvider:
        """获取供应商并校验权限。"""
        result = await db.execute(
            select(ModelProvider).where(
                and_(ModelProvider.id == provider_id, ModelProvider.user_id == user_id)
            )
        )
        provider = result.scalar_one_or_none()
        if provider is None:
            raise AppException(code="PROVIDER_NOT_FOUND", message="供应商不存在", status_code=404)
        return provider
