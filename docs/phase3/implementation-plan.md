# Phase 3 实现计划

## 目标

实现知识库管理（RAG）全链路：CRUD、文档上传、异步处理 Pipeline、向量检索。

## 完成清单

### 1. 数据层
- [x] 增强 `KnowledgeBase` / `KnowledgeDocument` / `KnowledgeChunk` 模型
- [x] `DocumentStatus` 新增 `pending`，新增 `FileType` 枚举
- [x] Alembic `004_phase3_knowledge_base.py`

### 2. 基础设施
- [x] `app/core/config.py` — 上传目录、Embedding 配置
- [x] `app/core/storage.py` — 文件存储
- [x] `app/core/celery_app.py` — Celery 配置

### 3. Pipeline
- [x] `text_extractor.py` / `text_chunker.py`
- [x] `embedding_service.py` / `document_processor.py`
- [x] `knowledge_tasks.py` — Celery 任务

### 4. 业务层与 API
- [x] `knowledge_service.py` / `vector_search_service.py`
- [x] `app/api/v1/knowledge.py` — 完整路由
- [x] 路由前缀 `/api/knowledge`
- [x] Agent 关联知识库（`knowledge_base_ids`）

### 5. 测试
- [x] `test_text_chunker.py` / `test_text_extractor.py`
- [x] `test_knowledge.py` / `test_vector_search.py`

## 本地验收

```bash
pip install -r requirements.txt
alembic upgrade head

# 终端 1：API
uvicorn app.main:app --reload --port 8000

# 终端 2：Celery Worker
celery -A app.core.celery_app worker --loglevel=info --queues=knowledge --concurrency=4

# 单元测试（无需 DB）
pytest tests/test_text_chunker.py tests/test_text_extractor.py -v

# 集成测试（需 PostgreSQL）
pytest tests/test_knowledge.py tests/test_vector_search.py -v
```

## 关键约束

- 文档处理异步执行，上传后状态为 `pending`
- Embedding 维度固定 1536（`text-embedding-3-small`）
- 分块配置变更后需重新处理已有文档
