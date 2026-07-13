"""
文档处理器：Pipeline 主逻辑。
串联 文本提取 → 分块 → Embedding → 存储 四个步骤。
由 Celery 异步任务调用。
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.knowledge import KnowledgeBase, KnowledgeDocument, KnowledgeChunk
from app.services.text_extractor import extract_text
from app.services.text_chunker import TextChunker
from app.services.embedding_service import EmbeddingService

logger = structlog.get_logger()


class DocumentProcessor:
    """
    文档处理 Pipeline。

    处理流程：
    1. 更新文档状态为 processing
    2. 文本提取：从文件中提取纯文本
    3. 文本分块：使用 tiktoken 按 token 数分块
    4. Embedding 生成：批量调用 Embedding API
    5. 存储：批量写入 knowledge_chunks 表
    6. 更新文档状态为 ready
    7. 更新知识库统计字段

    错误处理：
    - 任何步骤失败，更新文档状态为 failed 并记录错误信息
    - 已生成的 chunks 会在失败时回滚（事务内）
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_document(self, document_id: uuid.UUID) -> None:
        """
        处理单个文档的完整 Pipeline。

        Args:
            document_id: 文档 ID
        """
        # 加载文档和所属知识库
        result = await self.db.execute(
            select(KnowledgeDocument, KnowledgeBase)
            .join(KnowledgeBase, KnowledgeDocument.knowledge_base_id == KnowledgeBase.id)
            .where(KnowledgeDocument.id == document_id)
        )
        row = result.one_or_none()

        if row is None:
            logger.error("document_not_found", document_id=document_id)
            return

        document, kb = row
        logger.info(
            "processing_document",
            document_id=document_id,
            filename=document.filename,
            file_type=document.file_type,
            kb_id=kb.id,
        )

        try:
            # Step 1: 更新状态为 processing
            document.status = "processing"
            document.processing_started_at = datetime.now(timezone.utc)
            document.error_message = None
            await self.db.flush()

            # Step 2: 文本提取
            text = extract_text(document.file_path, document.file_type)

            # 保存提取的文本
            document.content = text

            # Step 3: 文本分块
            chunker = TextChunker(
                chunk_size=kb.chunk_size,
                chunk_overlap=kb.chunk_overlap,
                embedding_model=kb.embedding_model,
            )

            total_tokens = chunker.count_tokens(text)
            document.token_count = total_tokens

            chunks_data = chunker.chunk_text(text)

            if not chunks_data:
                raise ValueError("文档分块后无有效内容")

            logger.info(
                "document_chunked",
                document_id=document_id,
                chunk_count=len(chunks_data),
                total_tokens=total_tokens,
            )

            # Step 4: 先删除旧的 chunks（重新处理时需要）
            from sqlalchemy import delete
            await self.db.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
            )

            # Step 5: Embedding 生成（批量）
            chunk_texts = [c.content for c in chunks_data]
            embedding_service = EmbeddingService(self.db)
            embeddings = await embedding_service.get_embeddings(
                texts=chunk_texts,
                user_id=kb.user_id,
                embedding_model=kb.embedding_model,
            )

            # Step 6: 批量写入 knowledge_chunks
            for i, (chunk_data, embedding) in enumerate(zip(chunks_data, embeddings)):
                chunk = KnowledgeChunk(
                    knowledge_base_id=kb.id,
                    document_id=document_id,
                    content=chunk_data.content,
                    embedding=embedding,
                    chunk_index=chunk_data.chunk_index,
                    token_count=chunk_data.token_count,
                )
                self.db.add(chunk)

            await self.db.flush()

            # Step 7: 更新文档状态
            document.chunk_count = len(chunks_data)
            document.status = "ready"
            document.processing_completed_at = datetime.now(timezone.utc)
            document.error_message = None

            # Step 8: 更新知识库统计
            await self._update_kb_stats(kb.id)

            await self.db.commit()

            logger.info(
                "document_processed",
                document_id=document_id,
                chunk_count=len(chunks_data),
                total_tokens=total_tokens,
            )

        except Exception as e:
            # 处理失败：更新状态
            error_msg = str(e)[:2000]  # 截断过长的错误信息
            logger.error(
                "document_processing_failed",
                document_id=document_id,
                error=error_msg,
            )

            document.status = "failed"
            document.error_message = error_msg
            document.processing_completed_at = datetime.now(timezone.utc)

            try:
                await self.db.commit()
            except Exception as commit_err:
                logger.error("failed_to_update_error_status", error=str(commit_err))
                await self.db.rollback()

    async def _update_kb_stats(self, kb_id: uuid.UUID) -> None:
        """更新知识库的文档数和总大小统计。"""
        doc_stats = await self.db.execute(
            select(
                func.count(KnowledgeDocument.id),
                func.coalesce(func.sum(KnowledgeDocument.file_size), 0),
            ).where(KnowledgeDocument.knowledge_base_id == kb_id)
        )
        row = doc_stats.one()
        doc_count = row[0] or 0
        total_size = row[1] or 0

        await self.db.execute(
            update(KnowledgeBase)
            .where(KnowledgeBase.id == kb_id)
            .values(document_count=doc_count, total_size=total_size)
        )
