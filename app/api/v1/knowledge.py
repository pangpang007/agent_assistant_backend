"""知识库管理路由。"""

import uuid

from fastapi import APIRouter, UploadFile, File, Query, Depends

from app.api.deps import CurrentUser, DBSession
from app.core.exceptions import AppException
from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseConfigUpdate,
    SearchRequest,
)
from app.services.knowledge_service import KnowledgeService
from app.services.vector_search_service import VectorSearchService

router = APIRouter()


# ==================== 知识库 CRUD ====================

@router.get("")
async def list_knowledge_bases(
    session: DBSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str = Query(default=None, max_length=100),
):
    """获取知识库列表。"""
    result = await KnowledgeService.list_knowledge_bases(
        db=session,
        user_id=user.id,
        page=page,
        page_size=page_size,
        keyword=keyword,
    )
    return {"code": 0, "message": "success", "data": result}


@router.post("")
async def create_knowledge_base(
    session: DBSession,
    user: CurrentUser,
    body: KnowledgeBaseCreate,
):
    """创建知识库。"""
    kb = await KnowledgeService.create_knowledge_base(
        db=session,
        user_id=user.id,
        data=body.model_dump(exclude_none=True),
    )
    return {"code": 0, "message": "知识库创建成功", "data": kb}


@router.get("/{kb_id}")
async def get_knowledge_base(
    session: DBSession,
    user: CurrentUser,
    kb_id: uuid.UUID,
):
    """获取知识库详情。"""
    kb = await KnowledgeService.get_knowledge_base(
        db=session,
        kb_id=kb_id,
        current_user=user,
    )
    return {"code": 0, "message": "success", "data": kb}


@router.put("/{kb_id}")
async def update_knowledge_base(
    session: DBSession,
    user: CurrentUser,
    kb_id: uuid.UUID,
    body: KnowledgeBaseUpdate,
):
    """更新知识库。"""
    kb = await KnowledgeService.update_knowledge_base(
        db=session,
        kb_id=kb_id,
        current_user=user,
        data=body.model_dump(exclude_none=True),
    )
    return {"code": 0, "message": "知识库更新成功", "data": kb}


@router.delete("/{kb_id}")
async def delete_knowledge_base(
    session: DBSession,
    user: CurrentUser,
    kb_id: uuid.UUID,
):
    """删除知识库。"""
    result = await KnowledgeService.delete_knowledge_base(
        db=session,
        kb_id=kb_id,
        current_user=user,
    )
    return {"code": 0, "message": "知识库已删除", "data": result}


@router.put("/{kb_id}/config")
async def update_kb_config(
    session: DBSession,
    user: CurrentUser,
    kb_id: uuid.UUID,
    body: KnowledgeBaseConfigUpdate,
):
    """更新分块配置。"""
    result = await KnowledgeService.update_config(
        db=session,
        kb_id=kb_id,
        current_user=user,
        chunk_size=body.chunk_size,
        chunk_overlap=body.chunk_overlap,
    )
    return {"code": 0, "message": "分块配置已更新", "data": result}


# ==================== 文档管理 ====================

@router.get("/{kb_id}/documents")
async def list_documents(
    session: DBSession,
    user: CurrentUser,
    kb_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str = Query(default=None, pattern="^(pending|processing|ready|failed)$"),
):
    """获取文档列表。"""
    result = await KnowledgeService.list_documents(
        db=session,
        kb_id=kb_id,
        user_id=user.id,
        page=page,
        page_size=page_size,
        status=status,
    )
    return {"code": 0, "message": "success", "data": result}


@router.post("/{kb_id}/documents")
async def upload_document(
    session: DBSession,
    user: CurrentUser,
    kb_id: uuid.UUID,
    file: UploadFile = File(...),
):
    """上传文档。"""
    if not file.filename:
        raise AppException(code="NO_FILENAME", message="未提供文件名", status_code=400)

    file_content = await file.read()
    file_size = len(file_content)

    doc = await KnowledgeService.upload_document(
        db=session,
        kb_id=kb_id,
        user_id=user.id,
        filename=file.filename,
        file_content=file_content,
        file_size=file_size,
    )
    return {"code": 0, "message": "文档上传成功，正在处理中", "data": doc}


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(
    session: DBSession,
    user: CurrentUser,
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
):
    """删除文档。"""
    result = await KnowledgeService.delete_document(
        db=session,
        kb_id=kb_id,
        doc_id=doc_id,
        user_id=user.id,
    )
    return {"code": 0, "message": "文档已删除", "data": result}


@router.post("/{kb_id}/documents/{doc_id}/reprocess")
async def reprocess_document(
    session: DBSession,
    user: CurrentUser,
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
):
    """重新处理文档。"""
    doc = await KnowledgeService.reprocess_document(
        db=session,
        kb_id=kb_id,
        doc_id=doc_id,
        user_id=user.id,
    )
    return {"code": 0, "message": "文档已重新提交处理", "data": doc}


@router.get("/{kb_id}/documents/{doc_id}/status")
async def get_document_status(
    session: DBSession,
    user: CurrentUser,
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
):
    """查询文档处理状态。"""
    result = await KnowledgeService.get_document_status(
        db=session,
        kb_id=kb_id,
        doc_id=doc_id,
        user_id=user.id,
    )
    return {"code": 0, "message": "success", "data": result}


# ==================== 检索 ====================

@router.post("/{kb_id}/search")
async def search_knowledge_base(
    session: DBSession,
    user: CurrentUser,
    kb_id: uuid.UUID,
    body: SearchRequest,
):
    """检索知识库。"""
    search_service = VectorSearchService(db=session)
    result = await search_service.search(
        kb_id=kb_id,
        user_id=user.id,
        query=body.query,
        top_k=body.top_k,
    )
    return {"code": 0, "message": "success", "data": result}
