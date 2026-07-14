"""
向量检索服务：查询向量化 → pgvector 相似度搜索 → 返回 Top-K 文本块。
"""

import uuid
from typing import Optional

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from app.services.embedding_service import EmbeddingService

logger = structlog.get_logger()


class VectorSearchService:
    """
    向量检索服务。

    检索流程：
    1. 使用 EmbeddingService 将查询文本向量化
    2. 使用 pgvector 的余弦相似度操作符 (<=>) 搜索最近邻
    3. 关联查询文档信息（文件名等）
    4. 格式化返回结果
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(
        self,
        kb_id: uuid.UUID,
        user_id: uuid.UUID,
        query: str,
        top_k: int = 5,
    ) -> dict:
        """
        在指定知识库中检索与查询最相似的文本块。

        Args:
            kb_id: 知识库 ID
            user_id: 当前用户 ID
            query: 查询文本
            top_k: 返回结果数量（默认 5，最大 20）

        Returns:
            检索结果列表，每个元素包含：
            - content: 文本块内容
            - score: 相似度分数（0-1，1 为完全匹配）
            - chunk_index: 块序号
            - document_id: 来源文档 ID
            - filename: 来源文件名
            - token_count: 块的 token 数
        """
        # 参数限制
        top_k = min(max(top_k, 1), 20)

        # 校验知识库归属
        kb = await self._get_kb_with_permission(kb_id, user_id)

        # 空知识库：不调用 Embedding，快速返回空结果
        chunk_count = (
            await self.db.execute(
                select(func.count(KnowledgeChunk.id)).where(
                    KnowledgeChunk.knowledge_base_id == kb_id,
                    KnowledgeChunk.embedding.is_not(None),
                )
            )
        ).scalar() or 0
        if chunk_count == 0:
            return {"query": query, "total": 0, "results": []}

        # Step 1: 查询向量化
        embedding_service = EmbeddingService(self.db)
        query_embedding = await embedding_service.get_single_embedding(
            text=query,
            user_id=user_id,
            embedding_model=kb.embedding_model,
        )

        # Step 2: pgvector 相似度搜索
        # 使用余弦距离（<=>），分数 = 1 - 距离
        # 注意：pgvector 的 cosine_distance 返回 0-2 的值，0 表示完全相同
        results = await self._vector_search(
            kb_id=kb_id,
            query_embedding=query_embedding,
            top_k=top_k,
        )

        return {
            "query": query,
            "total": len(results),
            "results": results,
        }

    async def _vector_search(
        self,
        kb_id: uuid.UUID,
        query_embedding: list[float],
        top_k: int,
    ) -> list[dict]:
        """
        执行 pgvector 向量搜索。

        SQL 等价于：
        SELECT
            kc.id, kc.content, kc.chunk_index, kc.token_count,
            kc.document_id, kd.filename,
            1 - (kc.embedding <=> $1) AS score
        FROM knowledge_chunks kc
        JOIN knowledge_documents kd ON kc.document_id = kd.id
        WHERE kc.knowledge_base_id = $2
          AND kc.embedding IS NOT NULL
        ORDER BY kc.embedding <=> $1
        LIMIT $3
        """
        # 使用 SQLAlchemy text() 构建原生 SQL
        query = text("""
            SELECT
                kc.id AS chunk_id,
                kc.content,
                kc.chunk_index,
                kc.token_count,
                kc.document_id,
                kd.filename,
                1 - (kc.embedding <=> :query_embedding) AS score
            FROM knowledge_chunks kc
            JOIN knowledge_documents kd ON kc.document_id = kd.id
            WHERE kc.knowledge_base_id = :kb_id
              AND kc.embedding IS NOT NULL
              AND kd.status = 'ready'
            ORDER BY kc.embedding <=> :query_embedding
            LIMIT :top_k
        """)

        result = await self.db.execute(query, {
            "query_embedding": query_embedding,
            "kb_id": kb_id,
            "top_k": top_k,
        })

        rows = result.all()

        return [
            {
                "chunk_id": str(row.chunk_id),
                "content": row.content,
                "chunk_index": row.chunk_index,
                "token_count": row.token_count,
                "document_id": str(row.document_id),
                "filename": row.filename,
                "score": round(float(row.score), 6),
            }
            for row in rows
        ]

    async def _get_kb_with_permission(
        self, kb_id: uuid.UUID, user_id: uuid.UUID
    ) -> KnowledgeBase:
        """校验知识库归属。"""
        result = await self.db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == kb_id,
                KnowledgeBase.user_id == user_id,
            )
        )
        kb = result.scalar_one_or_none()

        if kb is None:
            raise AppException(
                code="KNOWLEDGE_BASE_NOT_FOUND",
                message="知识库不存在",
                status_code=404,
            )

        return kb
