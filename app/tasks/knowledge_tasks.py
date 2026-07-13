"""Celery 异步任务：文档处理 Pipeline。"""

import asyncio
import uuid

import structlog

from app.core.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(
    name="process_document",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_document_task(self, document_id: str):
    """文档处理 Celery 任务。"""
    doc_uuid = uuid.UUID(document_id)
    logger.info("celery_task_started", task_id=self.request.id, document_id=document_id)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_run_pipeline(doc_uuid))
        finally:
            loop.close()

        logger.info(
            "celery_task_completed", task_id=self.request.id, document_id=document_id
        )

    except (TimeoutError, ConnectionError) as e:
        logger.warning(
            "celery_task_retry",
            task_id=self.request.id,
            document_id=document_id,
            error=str(e),
            retry_count=self.request.retries,
        )
        raise self.retry(exc=e)

    except Exception as e:
        logger.error(
            "celery_task_failed",
            task_id=self.request.id,
            document_id=document_id,
            error=str(e),
        )


async def _run_pipeline(document_id: uuid.UUID) -> None:
    """在异步环境中运行 Pipeline。"""
    from app.core.database import async_session_factory
    from app.services.document_processor import DocumentProcessor

    async with async_session_factory() as db:
        processor = DocumentProcessor(db)
        await processor.process_document(document_id)
