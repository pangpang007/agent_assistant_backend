"""
Embedding 服务：调用用户已配置的模型供应商的 Embedding API。
支持 OpenAI 兼容接口（包括自定义 base_url）。
"""

import uuid
from typing import Optional

import httpx
import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.encryption import decrypt_value
from app.models.model_provider import ModelProvider, LLMModel

logger = structlog.get_logger()


class EmbeddingService:
    """
    Embedding 生成服务。

    策略：
    1. 优先使用用户已配置的模型供应商（通过知识库的 embedding_model 字段匹配）
    2. 如果用户未配置，使用系统默认的 Embedding 模型（.env 配置）
    3. 批量处理：每批 10-20 个 chunk（避免 API 限流）
    """

    # 支持的 Embedding 模型及其维度
    EMBEDDING_MODELS = {
        "text-embedding-3-small": {"dimensions": 1536, "provider_type": "openai"},
        "text-embedding-3-large": {"dimensions": 3072, "provider_type": "openai"},
        "text-embedding-ada-002": {"dimensions": 1536, "provider_type": "openai"},
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_embeddings(
        self,
        texts: list[str],
        user_id: uuid.UUID,
        embedding_model: str = "text-embedding-3-small",
    ) -> list[list[float]]:
        """
        批量获取文本的 Embedding 向量。

        Args:
            texts: 待向量化的文本列表
            user_id: 当前用户 ID（用于查找已配置的供应商）
            embedding_model: 使用的 Embedding 模型名称

        Returns:
            向量列表，每个向量为 float 列表

        Raises:
            AppException: API 调用失败或供应商未配置
        """
        if not texts:
            return []

        # 获取 API 配置
        api_key, base_url = await self._get_embedding_config(user_id, embedding_model)
        if not api_key:
            raise AppException(
                code="EMBEDDING_NOT_CONFIGURED",
                message="未配置 Embedding API Key，请先添加模型供应商或设置 DEFAULT_EMBEDDING_API_KEY",
                status_code=400,
            )

        # 分批处理
        all_embeddings = []
        batch_size = settings.embedding_batch_size  # 默认 20

        for batch_start in range(0, len(texts), batch_size):
            batch = texts[batch_start: batch_start + batch_size]

            logger.info(
                "embedding_batch",
                batch_start=batch_start,
                batch_size=len(batch),
                model=embedding_model,
            )

            embeddings = await self._call_embedding_api(
                texts=batch,
                api_key=api_key,
                base_url=base_url,
                model=embedding_model,
            )
            all_embeddings.extend(embeddings)

        return all_embeddings

    async def get_single_embedding(
        self,
        text: str,
        user_id: uuid.UUID,
        embedding_model: str = "text-embedding-3-small",
    ) -> list[float]:
        """
        获取单条文本 Embedding（用于检索时的查询向量化）。
        """
        embeddings = await self.get_embeddings([text], user_id, embedding_model)
        return embeddings[0]

    async def _get_embedding_config(
        self, user_id: uuid.UUID, embedding_model: str
    ) -> tuple[str, str]:
        """
        获取 Embedding API 的 api_key 和 base_url。

        查找顺序：
        1. 查找用户的供应商中是否有该 embedding 模型
        2. 如果没找到，使用系统默认配置
        """
        # 查找用户配置的供应商
        result = await self.db.execute(
            select(ModelProvider, LLMModel)
            .join(LLMModel, LLMModel.provider_id == ModelProvider.id)
            .where(
                and_(
                    ModelProvider.user_id == user_id,
                    ModelProvider.is_enabled == True,
                    LLMModel.model_name == embedding_model,
                    LLMModel.is_enabled == True,
                )
            )
        )
        row = result.one_or_none()

        if row:
            provider, model = row
            api_key = decrypt_value(provider.api_key_encrypted)
            base_url = provider.base_url or self._get_default_base_url(provider.provider_type)
            logger.info("using_user_provider", provider=provider.provider_name, model=embedding_model)
            return api_key, base_url

        # 回退到系统默认配置
        logger.info("using_default_embedding_config", model=embedding_model)
        return settings.default_embedding_api_key, settings.default_embedding_base_url

    async def _call_embedding_api(
        self,
        texts: list[str],
        api_key: str,
        base_url: str,
        model: str,
    ) -> list[list[float]]:
        """
        调用 OpenAI 兼容的 Embedding API。

        请求格式（OpenAI /v1/embeddings）：
        POST {base_url}/embeddings
        {
            "model": "text-embedding-3-small",
            "input": ["text1", "text2", ...]
        }

        响应格式：
        {
            "data": [
                {"embedding": [0.1, 0.2, ...], "index": 0},
                {"embedding": [0.3, 0.4, ...], "index": 1}
            ],
            "usage": {"prompt_tokens": 100, "total_tokens": 100}
        }
        """
        url = f"{base_url.rstrip('/')}/embeddings"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "input": texts,
        }

        try:
            async with httpx.AsyncClient(
                timeout=settings.embedding_request_timeout,
                verify=True,
            ) as client:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code == 401:
                    raise AppException(
                        code="EMBEDDING_AUTH_FAILED",
                        message="Embedding API 认证失败，请检查 API Key",
                        status_code=400,
                    )
                elif response.status_code == 429:
                    raise AppException(
                        code="EMBEDDING_RATE_LIMITED",
                        message="Embedding API 请求频率超限，请稍后重试",
                        status_code=429,
                    )
                elif response.status_code != 200:
                    error_body = response.text[:500]
                    raise AppException(
                        code="EMBEDDING_API_ERROR",
                        message=f"Embedding API 返回错误 ({response.status_code}): {error_body}",
                        status_code=502,
                    )

                data = response.json()
                embeddings_data = data.get("data", [])

                # 按 index 排序（API 可能乱序返回）
                embeddings_data.sort(key=lambda x: x.get("index", 0))

                return [item["embedding"] for item in embeddings_data]

        except httpx.TimeoutException:
            raise AppException(
                code="EMBEDDING_TIMEOUT",
                message="Embedding API 请求超时",
                status_code=504,
            )
        except httpx.RequestError as e:
            raise AppException(
                code="EMBEDDING_NETWORK_ERROR",
                message=f"Embedding API 网络错误: {str(e)}",
                status_code=502,
            )

    def _get_default_base_url(self, provider_type: str) -> str:
        """获取供应商类型的默认 base URL。"""
        defaults = {
            "openai": "https://api.openai.com/v1",
            "custom": settings.default_embedding_base_url or "https://api.openai.com/v1",
        }
        return defaults.get(provider_type, "https://api.openai.com/v1")
