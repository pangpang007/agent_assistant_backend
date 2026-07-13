"""知识库服务：处理知识库 CRUD、文档管理"""

import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy import select, func, delete, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.storage import get_document_storage_path, delete_document_file
from app.models.knowledge import KnowledgeBase, KnowledgeDocument, KnowledgeChunk
from app.models.user import User
from app.services.text_extractor import detect_file_type, validate_file_size


class KnowledgeService:

    # ==================== 知识库 CRUD ====================

    @staticmethod
    async def list_knowledge_bases(
        db: AsyncSession,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
    ) -> dict:
        """获取知识库列表。"""
        query = select(KnowledgeBase).where(KnowledgeBase.user_id == user_id)

        if keyword:
            query = query.where(
                or_(
                    KnowledgeBase.name.ilike(f"%{keyword}%"),
                    KnowledgeBase.description.ilike(f"%{keyword}%"),
                )
            )

        # 总数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页排序
        query = query.order_by(KnowledgeBase.updated_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        kbs = result.scalars().all()

        return {
            "items": kbs,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": page * page_size < total,
        }

    @staticmethod
    async def create_knowledge_base(
        db: AsyncSession,
        user_id: uuid.UUID,
        data: dict,
    ) -> KnowledgeBase:
        """创建知识库。"""
        # 校验 embedding_model（可选：检查是否支持）
        embedding_model = data.get("embedding_model", "text-embedding-3-small")

        kb = KnowledgeBase(
            user_id=user_id,
            **{k: v for k, v in data.items() if v is not None},
        )
        db.add(kb)
        await db.commit()
        await db.refresh(kb)
        return kb

    @staticmethod
    async def get_knowledge_base(
        db: AsyncSession,
        kb_id: uuid.UUID,
        current_user: User,
    ) -> KnowledgeBase:
        """获取知识库详情。"""
        kb = await KnowledgeService._get_kb_with_permission(db, kb_id, current_user.id)
        return kb

    @staticmethod
    async def update_knowledge_base(
        db: AsyncSession,
        kb_id: uuid.UUID,
        current_user: User,
        data: dict,
    ) -> KnowledgeBase:
        """更新知识库。"""
        kb = await KnowledgeService._get_kb_with_permission(db, kb_id, current_user.id)

        for key, value in data.items():
            if value is not None:
                setattr(kb, key, value)

        await db.commit()
        await db.refresh(kb)
        return kb

    @staticmethod
    async def delete_knowledge_base(
        db: AsyncSession,
        kb_id: uuid.UUID,
        current_user: User,
    ) -> dict:
        """删除知识库，级联删除文档和 chunks，同时删除物理文件。"""
        kb = await KnowledgeService._get_kb_with_permission(db, kb_id, current_user.id)

        # 查询文档信息（用于删除文件）
        doc_result = await db.execute(
            select(KnowledgeDocument.id, KnowledgeDocument.file_path)
            .where(KnowledgeDocument.knowledge_base_id == kb_id)
        )
        docs = doc_result.all()

        # 统计 chunk 数量
        chunk_count_result = await db.execute(
            select(func.count(KnowledgeChunk.id))
            .where(KnowledgeChunk.knowledge_base_id == kb_id)
        )
        deleted_chunks = chunk_count_result.scalar() or 0

        # 删除数据库记录
        db.delete(kb)  # cascade 自动删除 documents 和 chunks
        await db.commit()

        # 删除物理文件（数据库删除成功后再删文件）
        for doc_id, file_path in docs:
            try:
                delete_document_file(file_path)
            except Exception as e:
                # 文件删除失败不影响主流程
                import structlog
                structlog.get_logger().warning(
                    "file_delete_failed", file_path=file_path, error=str(e)
                )

        return {
            "kb_id": kb_id,
            "deleted_documents": len(docs),
            "deleted_chunks": deleted_chunks,
        }

    @staticmethod
    async def update_config(
        db: AsyncSession,
        kb_id: uuid.UUID,
        current_user: User,
        chunk_size: int,
        chunk_overlap: int,
    ) -> dict:
        """更新分块配置，已有文档标记为需要重新处理。"""
        kb = await KnowledgeService._get_kb_with_permission(db, kb_id, current_user.id)

        if chunk_overlap >= chunk_size:
            raise AppException(
                code="INVALID_CHUNK_CONFIG",
                message="chunk_overlap 必须小于 chunk_size",
                status_code=400,
            )

        kb.chunk_size = chunk_size
        kb.chunk_overlap = chunk_overlap

        # 将所有 ready 的文档标记为 pending，并删除旧 chunks
        result = await db.execute(
            select(KnowledgeDocument.id).where(
                and_(
                    KnowledgeDocument.knowledge_base_id == kb_id,
                    KnowledgeDocument.status == "ready",
                )
            )
        )
        affected_doc_ids = [row[0] for row in result.all()]

        if affected_doc_ids:
            # 删除旧 chunks
            await db.execute(
                delete(KnowledgeChunk).where(
                    KnowledgeChunk.document_id.in_(affected_doc_ids)
                )
            )

            # 重置文档状态
            await db.execute(
                update(KnowledgeDocument)
                .where(KnowledgeDocument.id.in_(affected_doc_ids))
                .values(
                    status="pending",
                    chunk_count=0,
                    error_message=None,
                    processing_started_at=None,
                    processing_completed_at=None,
                )
            )

            # 提交 Celery 任务重新处理
            from app.tasks.knowledge_tasks import process_document_task
            for doc_id in affected_doc_ids:
                process_document_task.delay(str(doc_id))

        await db.commit()

        return {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "affected_documents": len(affected_doc_ids),
        }

    # ==================== 文档管理 ====================

    @staticmethod
    async def list_documents(
        db: AsyncSession,
        kb_id: uuid.UUID,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> dict:
        """获取文档列表。"""
        await KnowledgeService._get_kb_with_permission(db, kb_id, user_id)

        query = select(KnowledgeDocument).where(
            KnowledgeDocument.knowledge_base_id == kb_id
        )

        if status:
            query = query.where(KnowledgeDocument.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(KnowledgeDocument.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        docs = result.scalars().all()

        return {
            "items": docs,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": page * page_size < total,
        }

    @staticmethod
    async def upload_document(
        db: AsyncSession,
        kb_id: uuid.UUID,
        user_id: uuid.UUID,
        filename: str,
        file_content: bytes,
        file_size: int,
    ) -> KnowledgeDocument:
        """上传文档。"""
        kb = await KnowledgeService._get_kb_with_permission(db, kb_id, user_id)

        # 检测文件类型
        file_type = detect_file_type(filename)
        if file_type is None:
            raise AppException(
                code="UNSUPPORTED_FILE_TYPE",
                message=f"不支持的文件类型，支持: PDF, TXT, MD, CSV, DOCX",
                status_code=400,
            )

        # 校验文件大小
        try:
            validate_file_size(file_size, file_type)
        except ValueError as e:
            raise AppException(
                code="FILE_TOO_LARGE",
                message=str(e),
                status_code=400,
            )

        # 校验文件非空
        if file_size == 0:
            raise AppException(
                code="EMPTY_FILE",
                message="文件为空",
                status_code=400,
            )

        # 保存文件
        file_path = get_document_storage_path(kb_id, filename)
        Path(file_path).write_bytes(file_content)

        # 创建文档记录
        doc = KnowledgeDocument(
            knowledge_base_id=kb_id,
            filename=filename,
            file_size=file_size,
            file_type=file_type,
            file_path=file_path,
            status="pending",
        )
        db.add(doc)
        await db.flush()

        # 更新知识库统计
        await db.execute(
            update(KnowledgeBase)
            .where(KnowledgeBase.id == kb_id)
            .values(
                document_count=KnowledgeBase.document_count + 1,
                total_size=KnowledgeBase.total_size + file_size,
            )
        )

        await db.commit()
        await db.refresh(doc)

        # 提交异步任务
        from app.tasks.knowledge_tasks import process_document_task
        process_document_task.delay(str(doc.id))

        return doc

    @staticmethod
    async def delete_document(
        db: AsyncSession,
        kb_id: uuid.UUID,
        doc_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict:
        """删除文档及其 chunks 和物理文件。"""
        kb = await KnowledgeService._get_kb_with_permission(db, kb_id, user_id)

        result = await db.execute(
            select(KnowledgeDocument).where(
                and_(
                    KnowledgeDocument.id == doc_id,
                    KnowledgeDocument.knowledge_base_id == kb_id,
                )
            )
        )
        doc = result.scalar_one_or_none()

        if doc is None:
            raise AppException(
                code="DOCUMENT_NOT_FOUND",
                message="文档不存在",
                status_code=404,
            )

        # 统计 chunk 数
        chunk_count_result = await db.execute(
            select(func.count(KnowledgeChunk.id))
            .where(KnowledgeChunk.document_id == doc_id)
        )
        deleted_chunks = chunk_count_result.scalar() or 0

        file_path = doc.file_path
        file_size = doc.file_size

        # 删除数据库记录
        db.delete(doc)

        # 更新知识库统计
        await db.execute(
            update(KnowledgeBase)
            .where(KnowledgeBase.id == kb_id)
            .values(
                document_count=func.greatest(KnowledgeBase.document_count - 1, 0),
                total_size=func.greatest(KnowledgeBase.total_size - file_size, 0),
            )
        )

        await db.commit()

        # 删除物理文件
        try:
            delete_document_file(file_path)
        except Exception:
            pass

        return {
            "document_id": doc_id,
            "deleted_chunks": deleted_chunks,
        }

    @staticmethod
    async def reprocess_document(
        db: AsyncSession,
        kb_id: uuid.UUID,
        doc_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> KnowledgeDocument:
        """重新处理文档。"""
        await KnowledgeService._get_kb_with_permission(db, kb_id, user_id)

        result = await db.execute(
            select(KnowledgeDocument).where(
                and_(
                    KnowledgeDocument.id == doc_id,
                    KnowledgeDocument.knowledge_base_id == kb_id,
                )
            )
        )
        doc = result.scalar_one_or_none()

        if doc is None:
            raise AppException(
                code="DOCUMENT_NOT_FOUND",
                message="文档不存在",
                status_code=404,
            )

        if doc.status == "processing":
            raise AppException(
                code="DOCUMENT_PROCESSING",
                message="文档正在处理中，无法重新处理",
                status_code=400,
            )

        # 删除旧 chunks
        await db.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id)
        )

        # 重置状态
        doc.status = "pending"
        doc.chunk_count = 0
        doc.token_count = 0
        doc.error_message = None
        doc.processing_started_at = None
        doc.processing_completed_at = None

        await db.commit()

        # 提交异步任务
        from app.tasks.knowledge_tasks import process_document_task
        process_document_task.delay(str(doc.id))

        return doc

    @staticmethod
    async def get_document_status(
        db: AsyncSession,
        kb_id: uuid.UUID,
        doc_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict:
        """获取文档处理状态。"""
        await KnowledgeService._get_kb_with_permission(db, kb_id, user_id)

        result = await db.execute(
            select(KnowledgeDocument).where(
                and_(
                    KnowledgeDocument.id == doc_id,
                    KnowledgeDocument.knowledge_base_id == kb_id,
                )
            )
        )
        doc = result.scalar_one_or_none()

        if doc is None:
            raise AppException(
                code="DOCUMENT_NOT_FOUND",
                message="文档不存在",
                status_code=404,
            )

        return {
            "id": doc.id,
            "status": doc.status,
            "chunk_count": doc.chunk_count,
            "token_count": doc.token_count,
            "error_message": doc.error_message,
            "processing_started_at": doc.processing_started_at,
            "processing_completed_at": doc.processing_completed_at,
        }

    # ==================== 内部方法 ====================

    @staticmethod
    async def _get_kb_with_permission(
        db: AsyncSession,
        kb_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> KnowledgeBase:
        """获取知识库并校验权限。"""
        result = await db.execute(
            select(KnowledgeBase).where(
                and_(
                    KnowledgeBase.id == kb_id,
                    KnowledgeBase.user_id == user_id,
                )
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
