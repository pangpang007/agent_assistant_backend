
import time
from typing import Any

from .base import BaseNodeExecutor, NodeExecutionResult, ExecutionContext


class KnowledgeRetrievalExecutor(BaseNodeExecutor):
    """
    知识检索节点执行器：从向量数据库中检索相关文本块。
    
    执行流程：
    1. 根据 config.knowledge_base_id 查询知识库
    2. 解析 query_template 获取查询文本
    3. 将查询文本向量化（调用 Embedding API）
    4. 使用 pgvector 进行相似度搜索
    5. 返回 Top-K 结果
    """

    async def execute(
        self,
        config: dict[str, Any],
        input_variables: dict[str, Any],
        context: ExecutionContext,
    ) -> NodeExecutionResult:
        start_time = time.time()

        try:
            kb_id = config.get("knowledge_base_id")
            if not kb_id:
                return NodeExecutionResult(error="knowledge_base_id is required", duration_ms=self._elapsed(start_time))

            # 获取查询文本
            query_template = config.get("query_template", "")
            query = self._resolve_template(query_template, input_variables)
            if not query:
                return NodeExecutionResult(error="Query text is empty", duration_ms=self._elapsed(start_time))

            top_k = config.get("top_k", 5)
            score_threshold = config.get("score_threshold", 0.0)

            # 向量化查询
            embedding = await self._get_embedding(query, context)
            if not embedding:
                return NodeExecutionResult(error="Failed to get embedding", duration_ms=self._elapsed(start_time))

            # pgvector 相似度搜索
            results = await self._vector_search(
                kb_id=kb_id,
                embedding=embedding,
                top_k=top_k,
                score_threshold=score_threshold,
                context=context,
            )

            output_key = config.get("output_key", "retrieved_docs")
            return NodeExecutionResult(
                output={output_key: results},
                duration_ms=self._elapsed(start_time),
            )

        except Exception as e:
            return NodeExecutionResult(error=str(e), duration_ms=self._elapsed(start_time))

    async def _get_embedding(self, text: str, context: ExecutionContext) -> list[float] | None:
        """调用 Embedding API 获取文本向量"""
        # TODO: Phase 3 实现时接入真实 Embedding API
        # 目前返回模拟向量用于调试
        import hashlib
        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16) % (10**6)
        return [float(hash_val + i) / 10**6 for i in range(1536)]

    async def _vector_search(
        self,
        kb_id: str,
        embedding: list[float],
        top_k: int,
        score_threshold: float,
        context: ExecutionContext,
    ) -> list[dict]:
        """使用 pgvector 进行余弦相似度搜索"""
        from sqlalchemy import text

        # pgvector 查询
        query = text("""
            SELECT 
                id, content, chunk_index,
                1 - (embedding <=> :query_embedding) AS similarity
            FROM knowledge_chunks
            WHERE knowledge_base_id = :kb_id
              AND embedding IS NOT NULL
            ORDER BY embedding <=> :query_embedding
            LIMIT :top_k
        """)

        result = await context.db_session.execute(query, {
            "query_embedding": str(embedding),
            "kb_id": kb_id,
            "top_k": top_k,
        })

        rows = result.fetchall()
        return [
            {
                "content": row.content,
                "chunk_index": row.chunk_index,
                "similarity": float(row.similarity),
            }
            for row in rows
            if float(row.similarity) >= score_threshold
        ]

    def _resolve_template(self, template: str, variables: dict) -> str:
        """解析模板字符串中的变量引用"""
        import re
        pattern = re.compile(r'\$\{([^}]+)\}')
        def replacer(match):
            var_name = match.group(1)
            if var_name.startswith("env."):
                return match.group(0)  # 环境变量在后续阶段解析
            return str(variables.get(var_name, match.group(0)))
        return pattern.sub(replacer, template)

    def _elapsed(self, start_time) -> int:
        return int((time.time() - start_time) * 1000)
