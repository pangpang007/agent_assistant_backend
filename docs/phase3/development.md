---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 4263223131904378_0/project_7661866342080954651-files/Phase3/phase3_backend.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 4263223131904378#1783935534161
    ReservedCode2: ""
---
# 汤圆的代码助手 - Phase 3 后端开发文档：知识库管理（RAG）

> **目标读者**：Cursor / AI Coding Agent  
> **版本**：Phase 3 v1.0  
> **项目代号**：`tangyuan-backend`  
> **前置条件**：Phase 0（脚手架 + 全部数据库模型）+ Phase 1（用户系统）+ Phase 2（Agent 管理 + 工具系统 + 模型管理）已完成

---

## 1. 目标

在 Phase 2 基础上实现知识库管理（RAG）全链路功能：

- **知识库 CRUD**：创建、查看、更新、删除知识库，配置分块参数
- **文档管理**：上传文档（PDF/TXT/MD/CSV/DOCX）、删除文档、重新处理文档、查询处理状态
- **文档处理 Pipeline**（核心）：上传 → 文本提取 → 分块 → Embedding → 存入 pgvector
- **向量检索**：查询向量化 → pgvector 相似度搜索 → 返回 Top-K 文本块
- **异步处理**：文档处理 Pipeline 通过 Celery + Redis 异步执行，实时更新文档状态

Phase 3 完成后，用户应能完成：创建知识库 → 上传文档 → 等待处理完成 → 检索测试的完整 RAG 流程。同时 Phase 2 中已建好的 `agent_knowledge_bases` 关联表被激活，Agent 配置中可关联知识库。

---

## 2. 技术栈（Phase 3 新增）

| 层面 | 技术选型 | 版本要求 | 用途 |
|------|---------|---------|------|
| 文档解析 | PyMuPDF (fitz) | 1.24+ | PDF 文本提取 |
| 文档解析 | python-docx | 1.1+ | DOCX 文本提取 |
| 分块 | tiktoken | 0.7+ | Token 级文本分块 |
| 向量存储 | pgvector | 0.2.5+ | PostgreSQL 向量扩展（Phase 0 已引入） |
| 异步任务 | Celery | 5.3+ | 分布式任务队列 |
| HTTP 客户端 | httpx | 0.27+ | 调用 Embedding API（Phase 0 已引入） |

---

## 3. 数据库变更

### 3.0 现有模型确认与修改

Phase 0 已经定义了 KnowledgeBase、KnowledgeDocument、KnowledgeChunk 三个模型。Phase 3 需要在 Phase 0 基础上做以下调整和确认。

#### 3.0.1 `app/models/knowledge.py` — Phase 3 完整模型

```python
import uuid
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Integer, Text, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin
from .enums import DocumentStatus


class KnowledgeBase(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "knowledge_bases"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Phase 3 新增：统计字段（冗余，避免每次 COUNT）
    document_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # total_size: 所有文档文件大小总和（bytes）

    # Embedding 配置
    embedding_model: Mapped[str] = mapped_column(
        String(100), nullable=False, default="text-embedding-3-small",
        server_default="text-embedding-3-small"
    )
    embedding_dimensions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1536, server_default="1536"
    )
    # Phase 3 新增 embedding_dimensions：支持不同维度模型（如 768/1536/3072）
    # 常用映射：text-embedding-3-small=1536, text-embedding-3-large=3072

    # 分块配置
    chunk_size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=512, server_default="512"
    )
    chunk_overlap: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50, server_default="50"
    )

    # Relationships
    user = relationship("User", back_populates="knowledge_bases")
    documents = relationship(
        "KnowledgeDocument", back_populates="knowledge_base",
        cascade="all, delete-orphan", lazy="selectin"
    )
    chunks = relationship("KnowledgeChunk", back_populates="knowledge_base", cascade="all, delete-orphan")
    agent_knowledge_bases = relationship(
        "AgentKnowledgeBase", back_populates="knowledge_base", cascade="all, delete-orphan"
    )


class KnowledgeDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "knowledge_documents"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    # file_type: "pdf" | "txt" | "md" | "csv" | "docx"

    # Phase 3 新增：提取后的原始文本（处理完成后填充，处理失败时可能为空）
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    chunk_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Phase 3 修改 status 枚举：新增 pending 状态
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending", index=True
    )
    # status 取值: "pending" | "processing" | "ready" | "failed"

    # Phase 3 新增：文件存储路径（服务器本地路径）
    file_path: Mapped[str] = mapped_column(String(2048), nullable=False)

    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Phase 3 新增：处理统计
    token_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # token_count: 文档总 token 数（分块前的 token 统计）

    processing_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    chunks = relationship("KnowledgeChunk", back_populates="document", cascade="all, delete-orphan")


class KnowledgeChunk(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "knowledge_chunks"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Phase 3 确认：向量维度由 embedding_dimensions 决定
    # 默认 1536 维（text-embedding-3-small），可通过知识库配置调整
    embedding = mapped_column(Vector(1536), nullable=True)

    # Phase 3 新增
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="chunks")
    document = relationship("KnowledgeDocument", back_populates="chunks")
```

**变更说明**：

| 变更项 | Phase 0 | Phase 3 |
|--------|---------|---------|
| KnowledgeBase.document_count | 无 | 新增，冗余统计 |
| KnowledgeBase.total_size | 无 | 新增，冗余统计 |
| KnowledgeBase.embedding_dimensions | 无 | 新增，支持不同维度模型 |
| KnowledgeDocument.file_type | 无 | 新增，显式记录文件类型 |
| KnowledgeDocument.content | 无 | 新增，提取后的原始文本 |
| KnowledgeDocument.status | 3 态 (processing/ready/failed) | 4 态 (pending/processing/ready/failed) |
| KnowledgeDocument.token_count | 无 | 新增，文档总 token 数 |
| KnowledgeDocument.processing_started_at | 无 | 新增，处理开始时间 |
| KnowledgeDocument.processing_completed_at | 无 | 新增，处理完成时间 |
| KnowledgeChunk.token_count | 无 | 新增，每个 chunk 的 token 数 |

### 3.1 枚举扩展

```python
# app/models/enums.py — Phase 3 修改

class DocumentStatus(str, enum.Enum):
    pending = "pending"          # Phase 3 新增：等待处理
    processing = "processing"    # 正在处理
    ready = "ready"              # 处理完成
    failed = "failed"            # 处理失败


# Phase 3 新增枚举
class FileType(str, enum.Enum):
    pdf = "pdf"
    txt = "txt"
    md = "md"
    csv = "csv"
    docx = "docx"
```

### 3.2 pgvector 扩展安装与向量索引

#### 3.2.1 pgvector 扩展安装

```sql
-- 在数据库中启用 pgvector 扩展（Alembic 迁移中执行）
CREATE EXTENSION IF NOT EXISTS vector;
```

#### 3.2.2 向量索引策略

**推荐 HNSW 索引**（构建慢但查询快，适合增量插入场景）：

```python
# 在 Alembic 迁移文件中添加：
from sqlalchemy import text

# HNSW 索引 — 余弦相似度
op.execute(
    "CREATE INDEX ix_knowledge_chunks_embedding_hnsw "
    "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops) "
    "WITH (m = 16, ef_construction = 64)"
)
```

**索引参数说明**：
- `m = 16`：每个节点的最大连接数（越大越精确，但内存占用越高）
- `ef_construction = 64`：构建时搜索范围（越大构建越慢但索引质量越好）

**注意**：
- HNSW 索引支持增量插入（新 chunk 可动态加入索引）
- 如果知识库数据量非常大（> 100 万 chunks），考虑按 `knowledge_base_id` 分区
- 对于少量数据的场景，也可以不建索引而使用暴力搜索（`<=>` 运算符）

#### 3.2.3 向量维度兼容性

```sql
-- 如果知识库配置了非 1536 维度的 embedding 模型，需要创建对应维度的列
-- 方案 A（推荐）：统一使用 1536 维，通过知识库的 embedding_model 字段决定调用哪个模型
-- 方案 B（灵活）：使用最大维度列，不同维度模型通过 padding 补齐（不推荐，浪费存储）

-- 本方案采用方案 A：固定 1536 维，embedding_dimensions 字段仅用于记录
-- 如果用户选择了 3072 维的模型（如 text-embedding-3-large），需要将 Vector(1536) 改为 Vector(3072)
-- 这需要在创建知识库时动态决定，或者统一使用最大维度
```

**实际建议**：Phase 3 统一使用 `Vector(1536)`，对应 `text-embedding-3-small`。如果后续需要支持 3072 维模型，通过 Alembic 迁移调整列定义。

### 3.3 Alembic 迁移

```bash
alembic revision --autogenerate -m "phase3_knowledge_base_enhancement"
alembic upgrade head
```

迁移内容摘要：

1. **knowledge_bases 表**：新增 `document_count`、`total_size`、`embedding_dimensions` 列
2. **knowledge_documents 表**：新增 `file_type`、`content`、`token_count`、`processing_started_at`、`processing_completed_at` 列；`status` 默认值从 `processing` 改为 `pending`
3. **knowledge_chunks 表**：新增 `token_count` 列
4. **向量索引**：创建 HNSW 索引
5. **枚举更新**：`DocumentStatus` 新增 `pending` 值

---

## 4. 文档处理 Pipeline 详细设计

### 4.0 总体架构

```
上传文件 → 保存文件 → 创建 Document 记录 (status=pending)
                        ↓
                 提交异步任务到 Celery
                        ↓
            ┌─────── Pipeline Worker ────────┐
            │                                 │
            │  1. 更新 status=processing      │
            │  2. 文本提取（TextExtractor）    │
            │  3. 文本分块（TextChunker）      │
            │  4. Embedding 生成              │
            │  5. 批量写入 knowledge_chunks   │
            │  6. 更新 status=ready           │
            │  7. 更新知识库统计字段           │
            │                                 │
            │  异常 → status=failed + 错误信息 │
            └─────────────────────────────────┘
```

### 4.1 文本提取 `app/services/text_extractor.py`

```python
"""
文本提取器：从不同类型的文件中提取纯文本。
每种文件类型对应一个提取方法。
"""

import csv
import io
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()

# 支持的文件类型及最大大小限制（bytes）
MAX_FILE_SIZES = {
    "pdf": 50 * 1024 * 1024,     # 50 MB
    "txt": 10 * 1024 * 1024,     # 10 MB
    "md": 10 * 1024 * 1024,      # 10 MB
    "csv": 20 * 1024 * 1024,     # 20 MB
    "docx": 30 * 1024 * 1024,    # 30 MB
}

SUPPORTED_EXTENSIONS = {
    ".pdf": "pdf",
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
    ".csv": "csv",
    ".docx": "docx",
}


def detect_file_type(filename: str) -> Optional[str]:
    """
    根据文件扩展名检测文件类型。
    返回文件类型字符串或 None（不支持的类型）。
    """
    ext = Path(filename).suffix.lower()
    return SUPPORTED_EXTENSIONS.get(ext)


def validate_file_size(file_size: int, file_type: str) -> None:
    """
    校验文件大小是否在允许范围内。
    超出限制时抛出 ValueError。
    """
    max_size = MAX_FILE_SIZES.get(file_type, 10 * 1024 * 1024)
    if file_size > max_size:
        max_mb = max_size // (1024 * 1024)
        raise ValueError(f"文件大小超出限制，{file_type} 类型最大允许 {max_mb}MB")


def extract_text(file_path: str, file_type: str) -> str:
    """
    根据文件类型分发到对应的文本提取方法。

    Args:
        file_path: 文件的本地存储路径
        file_type: 文件类型 ("pdf", "txt", "md", "csv", "docx")

    Returns:
        提取出的纯文本字符串

    Raises:
        ValueError: 不支持的文件类型
        FileNotFoundError: 文件不存在
        Exception: 提取过程中的其他错误
    """
    extractors = {
        "pdf": _extract_pdf,
        "txt": _extract_txt,
        "md": _extract_txt,     # Markdown 按纯文本处理
        "csv": _extract_csv,
        "docx": _extract_docx,
    }

    extractor = extractors.get(file_type)
    if extractor is None:
        raise ValueError(f"不支持的文件类型: {file_type}")

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    logger.info("extracting_text", file_path=file_path, file_type=file_type)
    text = extractor(path)

    # 基础清洗
    text = _clean_text(text)

    if not text.strip():
        raise ValueError("文件内容为空或无法提取有效文本")

    logger.info("text_extracted", file_path=file_path, char_count=len(text))
    return text


def _extract_pdf(path: Path) -> str:
    """
    使用 PyMuPDF (fitz) 提取 PDF 文本。

    PyMuPDF 优势：
    - 速度快（C 语言底层）
    - 支持复杂 PDF 布局
    - 可处理多页文档
    """
    import fitz  # PyMuPDF

    text_parts = []
    doc = fitz.open(str(path))

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text("text")
            if page_text.strip():
                # 每页之间加分隔符
                text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}")
    finally:
        doc.close()

    return "\n\n".join(text_parts)


def _extract_txt(path: Path) -> str:
    """
    直接读取 TXT/Markdown 文件。
    尝试多种编码，优先 UTF-8。
    """
    encodings = ["utf-8", "gbk", "gb2312", "latin-1"]

    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue

    # 最后尝试二进制读取
    raise ValueError(f"无法解码文件，支持的编码: {encodings}")


def _extract_csv(path: Path) -> str:
    """
    CSV 文件逐行转文本。
    将每行数据转为 "列名: 值" 的格式，保留结构化信息。
    """
    text_parts = []
    encodings = ["utf-8", "gbk", "gb2312", "latin-1"]
    content = None

    for encoding in encodings:
        try:
            content = path.read_text(encoding=encoding)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if content is None:
        raise ValueError("无法解码 CSV 文件")

    reader = csv.DictReader(io.StringIO(content))

    if not reader.fieldnames:
        raise ValueError("CSV 文件没有表头")

    for row_num, row in enumerate(reader, 1):
        row_text = f"Row {row_num}: " + ", ".join(
            f"{key}: {value}" for key, value in row.items() if value
        )
        text_parts.append(row_text)

    return "\n".join(text_parts)


def _extract_docx(path: Path) -> str:
    """
    使用 python-docx 提取 DOCX 文档文本。
    提取所有段落文本和表格文本。
    """
    from docx import Document

    doc = Document(str(path))
    text_parts = []

    # 提取段落
    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)

    # 提取表格
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(
                cell.text.strip() for cell in row.cells if cell.text.strip()
            )
            if row_text:
                text_parts.append(row_text)

    return "\n\n".join(text_parts)


def _clean_text(text: str) -> str:
    """
    基础文本清洗：
    1. 去除连续多个空行（超过 2 个空行合并为 2 个）
    2. 去除行首行尾空白
    3. 替换特殊空白字符
    """
    import re

    # 替换特殊空白字符
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ")
    text = text.replace("\u00a0", " ")  # non-breaking space

    # 去除连续多行空白
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 去除每行首尾空白
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()
```

### 4.2 文本分块 `app/services/text_chunker.py`

```python
"""
文本分块器：使用 tiktoken 按 token 数分块。
支持配置 chunk_size 和 chunk_overlap。
"""

from typing import NamedTuple

import structlog
import tiktoken

logger = structlog.get_logger()


class ChunkResult(NamedTuple):
    """分块结果"""
    content: str        # 块的文本内容
    chunk_index: int    # 块序号（从 0 开始）
    token_count: int    # 该块的 token 数


class TextChunker:
    """
    基于 tiktoken 的文本分块器。

    分块策略：
    1. 使用指定的 encoding 模型进行 token 计数
    2. 按 chunk_size（token 数）切分文本
    3. 相邻块之间保留 chunk_overlap 个 token 的重叠
    4. 尽量在段落/句子边界切分（避免从单词中间断开）
    """

    # tiktoken encoding 名称映射
    ENCODING_MAP = {
        "text-embedding-3-small": "cl100k_base",
        "text-embedding-3-large": "cl100k_base",
        "text-embedding-ada-002": "cl100k_base",
    }

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        embedding_model: str = "text-embedding-3-small",
    ):
        """
        Args:
            chunk_size: 每个块的目标 token 数
            chunk_overlap: 相邻块之间的重叠 token 数
            embedding_model: embedding 模型名称，用于确定 encoding
        """
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) 必须小于 chunk_size ({chunk_size})"
            )

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # 获取 tiktoken encoding
        encoding_name = self.ENCODING_MAP.get(embedding_model, "cl100k_base")
        try:
            self.encoding = tiktoken.get_encoding(encoding_name)
        except Exception:
            logger.warning(
                "tiktoken_encoding_not_found, fallback_to_cl100k_base",
                embedding_model=embedding_model,
            )
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """计算文本的 token 数。"""
        return len(self.encoding.encode(text))

    def chunk_text(self, text: str) -> list[ChunkResult]:
        """
        将文本分块。

        算法：
        1. 先将文本按段落分割为段落列表
        2. 使用贪心策略，将段落逐步合并到当前块中
        3. 当当前块的 token 数超过 chunk_size 时，开始新块
        4. 如果单个段落超过 chunk_size，使用 token 级切分
        5. 相邻块保留 chunk_overlap 个 token 的重叠

        Returns:
            ChunkResult 列表
        """
        if not text.strip():
            return []

        # 第一步：按段落分割
        paragraphs = self._split_into_paragraphs(text)

        # 第二步：贪心合并段落为块
        raw_chunks = self._merge_paragraphs(paragraphs)

        # 第三步：添加重叠
        chunks_with_overlap = self._add_overlap(raw_chunks)

        # 第四步：构造结果
        results = []
        for idx, chunk_content in enumerate(chunks_with_overlap):
            token_count = self.count_tokens(chunk_content)
            if token_count > 0:
                results.append(ChunkResult(
                    content=chunk_content.strip(),
                    chunk_index=idx,
                    token_count=token_count,
                ))

        logger.info(
            "text_chunked",
            total_tokens=sum(c.token_count for c in results),
            chunk_count=len(results),
        )

        return results

    def _split_into_paragraphs(self, text: str) -> list[str]:
        """
        将文本按段落分割。
        段落之间以双换行分隔。
        """
        paragraphs = text.split("\n\n")
        return [p.strip() for p in paragraphs if p.strip()]

    def _merge_paragraphs(self, paragraphs: list[str]) -> list[str]:
        """
        贪心合并段落为块。
        每个块的 token 数不超过 chunk_size。
        """
        if not paragraphs:
            return []

        chunks = []
        current_chunk_parts = []
        current_token_count = 0

        for para in paragraphs:
            para_tokens = self.count_tokens(para)

            if para_tokens > self.chunk_size:
                # 单个段落超过 chunk_size，需要先存入当前块，再 token 级切分段落
                if current_chunk_parts:
                    chunks.append("\n\n".join(current_chunk_parts))
                    current_chunk_parts = []
                    current_token_count = 0

                # Token 级切分超长段落
                sub_chunks = self._split_long_text(para)
                chunks.extend(sub_chunks)
                continue

            if current_token_count + para_tokens > self.chunk_size:
                # 当前块已满，存入结果并开始新块
                chunks.append("\n\n".join(current_chunk_parts))
                current_chunk_parts = [para]
                current_token_count = para_tokens
            else:
                # 追加到当前块
                current_chunk_parts.append(para)
                current_token_count += para_tokens

        # 最后一个块
        if current_chunk_parts:
            chunks.append("\n\n".join(current_chunk_parts))

        return chunks

    def _split_long_text(self, text: str) -> list[str]:
        """
        Token 级切分超长文本。
        按 token 数切分，尽量在句子边界断开。
        """
        tokens = self.encoding.encode(text)
        chunks = []
        start = 0

        while start < len(tokens):
            end = start + self.chunk_size

            # 尝试在句子边界切分
            if end < len(tokens):
                # 从 end 位置往回找句子边界（. ! ? \n）
                boundary = self._find_sentence_boundary(tokens, start, end)
                if boundary > start:
                    end = boundary

            chunk_tokens = tokens[start:end]
            chunk_text = self.encoding.decode(chunk_tokens)
            chunks.append(chunk_text.strip())

            start = end

        return [c for c in chunks if c]

    def _find_sentence_boundary(
        self, tokens: list[int], start: int, end: int
    ) -> int:
        """
        在 tokens[start:end] 范围内查找最后一个句子边界。
        句子边界标记：. ! ? 后跟空格或结尾。
        返回句子边界处的 token 索引（不含边界 token）。
        如果找不到句子边界，返回 end。
        """
        # 解码 end 附近的文本，查找句子边界
        search_range = max(start, end - 50)  # 搜索最后 50 个 token
        search_tokens = tokens[search_range:end]
        search_text = self.encoding.decode(search_tokens)

        # 查找最后一个句子结束符
        for marker in [".\n", "!\n", "?\n", ". ", "! ", "? "]:
            last_pos = search_text.rfind(marker)
            if last_pos > 0:
                # 计算对应的 token 位置
                prefix_text = search_text[: last_pos + len(marker)]
                prefix_tokens = self.encoding.encode(prefix_text)
                boundary = search_range + len(prefix_tokens)
                if boundary > start:
                    return boundary

        return end

    def _add_overlap(self, chunks: list[str]) -> list[str]:
        """
        为相邻块添加重叠。
        后一个块的开头 overlap_tokens 个 token 与前一个块的末尾相同。
        """
        if len(chunks) <= 1:
            return chunks

        result = [chunks[0]]

        for i in range(1, len(chunks)):
            prev_text = chunks[i - 1]
            curr_text = chunks[i]

            # 获取前一个块末尾的 overlap 个 token
            prev_tokens = self.encoding.encode(prev_text)
            overlap_tokens = prev_tokens[-self.chunk_overlap:] if len(prev_tokens) >= self.chunk_overlap else prev_tokens

            if overlap_tokens:
                overlap_text = self.encoding.decode(overlap_tokens)
                # 将重叠文本添加到当前块的开头
                result.append(overlap_text.strip() + "\n" + curr_text)
            else:
                result.append(curr_text)

        return result
```

### 4.3 Embedding 服务 `app/services/embedding_service.py`

```python
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
```

### 4.4 Pipeline 主处理器 `app/services/document_processor.py`

```python
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
```

### 4.5 异步任务定义 `app/tasks/knowledge_tasks.py`

```python
"""
Celery 异步任务：文档处理 Pipeline。
"""

import asyncio
import uuid

import structlog
from celery import shared_task

from app.core.config import settings

logger = structlog.get_logger()


@shared_task(
    name="process_document",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_document_task(self, document_id: str):
    """
    文档处理 Celery 任务。

    参数:
        document_id: 文档 UUID 字符串

    重试策略:
        - 最多重试 2 次
        - 重试间隔 30 秒
        - Embedding API 超时/限流错误可重试
        - 文本提取/分块错误不重试（数据问题）
    """
    doc_uuid = uuid.UUID(document_id)
    logger.info("celery_task_started", task_id=self.request.id, document_id=document_id)

    try:
        # 在 Celery worker 中运行异步代码
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_run_pipeline(doc_uuid))
        finally:
            loop.close()

        logger.info("celery_task_completed", task_id=self.request.id, document_id=document_id)

    except (TimeoutError, ConnectionError) as e:
        # 网络/超时类错误可以重试
        logger.warning(
            "celery_task_retry",
            task_id=self.request.id,
            document_id=document_id,
            error=str(e),
            retry_count=self.request.retries,
        )
        raise self.retry(exc=e)

    except Exception as e:
        # 其他错误不重试
        logger.error(
            "celery_task_failed",
            task_id=self.request.id,
            document_id=document_id,
            error=str(e),
        )
        # 更新文档状态为 failed（pipeline 内部已处理）


async def _run_pipeline(document_id: uuid.UUID) -> None:
    """在异步环境中运行 Pipeline。"""
    from app.core.database import async_session_factory
    from app.services.document_processor import DocumentProcessor

    async with async_session_factory() as db:
        processor = DocumentProcessor(db)
        await processor.process_document(document_id)
```

### 4.6 文件存储

#### 4.6.1 文件存储目录

```python
# app/core/storage.py

"""
文件存储管理：处理上传文件的存储和清理。
"""

import os
import uuid
from pathlib import Path

from app.core.config import settings


def get_upload_dir() -> Path:
    """获取上传文件根目录。"""
    upload_dir = Path(settings.upload_base_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def get_document_storage_path(kb_id: uuid.UUID, filename: str) -> str:
    """
    生成文档存储路径。
    格式: {upload_base_dir}/{kb_id}/{uuid4}_{filename}

    按知识库分目录，文件名前加 UUID 避免冲突。
    """
    kb_dir = get_upload_dir() / str(kb_id)
    kb_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex}_{filename}"
    return str(kb_dir / safe_name)


def delete_document_file(file_path: str) -> None:
    """删除文档文件。"""
    path = Path(file_path)
    if path.exists():
        path.unlink()

        # 如果知识库目录为空，清理目录
        parent = path.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
```

---

## 5. 异步任务设计

### 5.1 技术选型：Celery + Redis（推荐）

**选择 Celery 而非 BackgroundTasks 的理由**：

| 维度 | Celery + Redis | BackgroundTasks |
|------|---------------|-----------------|
| 可靠性 | ✅ 任务持久化，Worker 崩溃后自动重试 | ❌ 请求结束任务丢失 |
| 可扩展 | ✅ 多 Worker 水平扩展 | ❌ 单进程阻塞 |
| 状态查询 | ✅ 任务队列 + 数据库双状态 | ❌ 无标准机制 |
| 监控 | ✅ Flower 监控面板 | ❌ 无 |
| 资源隔离 | ✅ 独立 Worker 进程 | ❌ 占用 API 进程资源 |
| 复杂度 | 需要额外部署 Worker | 零额外部署 |

**结论**：文档处理是 CPU + IO 密集型任务，需要可靠性保证，Celery 是正确选择。

### 5.2 Celery 配置 `app/core/celery_app.py`

```python
"""Celery 应用配置。"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "tangyuan",
    broker=settings.redis_url,        # 复用 Redis 作为消息代理
    backend=settings.redis_url,        # 结果后端
    include=["app.tasks.knowledge_tasks"],
)

celery_app.conf.update(
    # 序列化
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # 时区
    timezone="UTC",
    enable_utc=True,

    # Worker 配置
    worker_concurrency=4,             # 并发 Worker 数
    worker_max_tasks_per_child=50,    # 每个 Worker 处理 50 个任务后重启（防止内存泄漏）
    worker_prefetch_multiplier=1,     # 每次只预取 1 个任务（文档处理耗时长）

    # 任务路由
    task_routes={
        "process_document": {"queue": "knowledge"},
    },

    # 任务超时
    task_soft_time_limit=300,   # 软超时 5 分钟（抛出 SoftTimeLimitExceeded）
    task_time_limit=600,        # 硬超时 10 分钟（强制终止）

    # 结果过期
    result_expires=3600,        # 结果保留 1 小时
)
```

### 5.3 启动命令

```bash
# 启动 Celery Worker（开发环境）
celery -A app.core.celery_app worker --loglevel=info --queues=knowledge --concurrency=4

# 启动 Celery Worker（生产环境，使用 gevent 协程池提高并发）
celery -A app.core.celery_app worker --loglevel=warning --queues=knowledge --pool=gevent --concurrency=100

# 启动 Flower 监控面板（可选）
celery -A app.core.celery_app flower --port=5555
```

### 5.4 状态更新机制

```
文档上传 → status=pending → 提交 Celery 任务
                                    ↓
                            Worker 接收任务 → status=processing
                                    ↓
                            Pipeline 完成 → status=ready
                            Pipeline 失败 → status=failed

前端轮询：GET /api/knowledge/:kb_id/documents/:doc_id/status
每 2 秒查询一次，直到 status 为 ready 或 failed。
```

### 5.5 依赖安装

```
# requirements.txt 新增
celery>=5.3.0
PyMuPDF>=1.24.0
python-docx>=1.1.0
tiktoken>=0.7.0
```

---

## 6. 检索实现

### 6.1 `app/services/vector_search_service.py`

```python
"""
向量检索服务：查询向量化 → pgvector 相似度搜索 → 返回 Top-K 文本块。
"""

import uuid
from typing import Optional

import structlog
from sqlalchemy import select, text
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
```

---

## 7. Pydantic Schemas

### 7.1 `app/schemas/knowledge.py` — Phase 3 完整版

```python
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ========== KnowledgeBase Schemas ==========

class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    embedding_model: str = Field(default="text-embedding-3-small", max_length=100)
    chunk_size: int = Field(default=512, ge=100, le=10000)
    chunk_overlap: int = Field(default=50, ge=0, le=2000)


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)


class KnowledgeBaseConfigUpdate(BaseModel):
    """更新分块配置"""
    chunk_size: int = Field(..., ge=100, le=10000)
    chunk_overlap: int = Field(..., ge=0, le=2000)

    @classmethod
    def validate_overlap(cls, v, info):
        chunk_size = info.data.get("chunk_size")
        if chunk_size and v >= chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        return v


class KnowledgeBaseResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: Optional[str] = None
    document_count: int = 0
    total_size: int = 0
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeBaseListItem(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    document_count: int = 0
    total_size: int = 0
    embedding_model: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeBaseListResponse(BaseModel):
    items: list[KnowledgeBaseListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


# ========== KnowledgeDocument Schemas ==========

class KnowledgeDocumentResponse(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    filename: str
    file_size: int
    file_type: str
    chunk_count: int
    token_count: int = 0
    status: str
    error_message: Optional[str] = None
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeDocumentStatusResponse(BaseModel):
    """文档处理状态响应（用于轮询）"""
    id: uuid.UUID
    status: str
    chunk_count: int = 0
    token_count: int = 0
    error_message: Optional[str] = None
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None


class KnowledgeDocumentListResponse(BaseModel):
    items: list[KnowledgeDocumentResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


# ========== Search Schemas ==========

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResultItem(BaseModel):
    chunk_id: str
    content: str
    chunk_index: int
    token_count: int
    document_id: str
    filename: str
    score: float


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResultItem]
```

---

## 8. API 完整规格

### 8.0 通用约定

#### 成功响应格式

```json
{
    "code": 0,
    "message": "success",
    "data": { ... }
}
```

#### 认证方式

所有接口需要 `Authorization: Bearer <access_token>` 请求头。

#### 文件上传限制

| 文件类型 | 最大大小 |
|---------|---------|
| PDF | 50 MB |
| TXT/MD | 10 MB |
| CSV | 20 MB |
| DOCX | 30 MB |

---

### 8.1 知识库 CRUD API

#### 8.1.1 获取知识库列表

**`GET /api/knowledge`**

**描述**：获取当前用户的知识库列表，支持分页。

**权限**：需要登录。

**查询参数**：

```python
page: int = 1           # 页码
page_size: int = 20     # 每页数量（1-100）
keyword: Optional[str]  # 搜索关键词（模糊匹配 name 和 description）
```

**业务逻辑**：

1. 获取当前用户
2. 查询 `knowledge_bases` 表：`WHERE user_id = current_user.id`
3. 如有 `keyword`：`AND (name ILIKE '%keyword%' OR description ILIKE '%keyword%')`
4. 按 `updated_at DESC` 排序
5. 分页查询

**响应体**：

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "items": [
            {
                "id": "uuid",
                "name": "我的知识库",
                "description": "...",
                "document_count": 5,
                "total_size": 1048576,
                "embedding_model": "text-embedding-3-small",
                "created_at": "2026-07-13T10:00:00Z",
                "updated_at": "2026-07-13T12:00:00Z"
            }
        ],
        "total": 5,
        "page": 1,
        "page_size": 20,
        "has_next": false
    }
}
```

---

#### 8.1.2 创建知识库

**`POST /api/knowledge`**

**描述**：创建新的知识库。

**权限**：需要登录。

**请求体**：

```json
{
    "name": "我的知识库",
    "description": "用于存储产品文档",
    "embedding_model": "text-embedding-3-small",
    "chunk_size": 512,
    "chunk_overlap": 50
}
```

**业务逻辑**：

1. 获取当前用户
2. 校验请求体
3. 检查同一用户下是否有同名知识库（可选：允许同名或唯一约束）
4. 创建 `KnowledgeBase` 记录
5. 返回新建知识库信息

**响应体**：`KnowledgeBaseResponse`

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 400 | `INVALID_EMBEDDING_MODEL` | 不支持的 Embedding 模型 |
| 422 | `VALIDATION_ERROR` | 参数校验失败 |

---

#### 8.1.3 获取知识库详情

**`GET /api/knowledge/:id`**

**描述**：获取知识库详细信息。

**业务逻辑**：查询知识库，权限检查（`user_id == current_user.id`），返回详情。

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `KNOWLEDGE_BASE_NOT_FOUND` | 知识库不存在 |
| 403 | `FORBIDDEN` | 无权访问 |

---

#### 8.1.4 更新知识库

**`PUT /api/knowledge/:id`**

**描述**：更新知识库名称和描述。

**请求体**：

```json
{
    "name": "新名称",
    "description": "新描述"
}
```

**业务逻辑**：权限检查 → 更新字段 → 返回更新后信息。

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `KNOWLEDGE_BASE_NOT_FOUND` | 知识库不存在 |
| 403 | `FORBIDDEN` | 无权修改 |

---

#### 8.1.5 删除知识库

**`DELETE /api/knowledge/:id`**

**描述**：删除知识库，级联删除所有文档和 chunks，同时删除物理文件。

**业务逻辑**：

1. 权限检查
2. 查询所有文档的 `file_path`
3. 删除知识库（`cascade="all, delete-orphan"` 自动删除文档和 chunks）
4. 遍历文件路径，删除物理文件
5. 清理空目录

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `KNOWLEDGE_BASE_NOT_FOUND` | 知识库不存在 |
| 403 | `FORBIDDEN` | 无权删除 |

**响应体**：

```json
{
    "code": 0,
    "message": "知识库已删除",
    "data": {
        "kb_id": "uuid",
        "deleted_documents": 5,
        "deleted_chunks": 120
    }
}
```

---

#### 8.1.6 更新分块配置

**`PUT /api/knowledge/:id/config`**

**描述**：更新知识库的分块参数（chunk_size, chunk_overlap）。更新后，已有的文档需要重新处理才能生效。

**请求体**：

```json
{
    "chunk_size": 1024,
    "chunk_overlap": 100
}
```

**业务逻辑**：

1. 权限检查
2. 校验 `chunk_overlap < chunk_size`
3. 更新配置
4. 将所有 `status=ready` 的文档标记为需要重新处理（设为 `pending` 状态）
5. 删除旧的 chunks
6. 返回更新后的配置

**响应体**：

```json
{
    "code": 0,
    "message": "分块配置已更新，已有文档需要重新处理",
    "data": {
        "chunk_size": 1024,
        "chunk_overlap": 100,
        "affected_documents": 3
    }
}
```

---

### 8.2 文档管理 API

#### 8.2.1 获取文档列表

**`GET /api/knowledge/:id/documents`**

**描述**：获取指定知识库下的文档列表，支持分页和状态筛选。

**查询参数**：

```python
page: int = 1
page_size: int = 20
status: Optional[str]  # "pending" | "processing" | "ready" | "failed"
```

**业务逻辑**：

1. 校验知识库归属
2. 按 `created_at DESC` 排序
3. 如有 `status` 筛选

**响应体**：`KnowledgeDocumentListResponse`

---

#### 8.2.2 上传文档

**`POST /api/knowledge/:id/documents`**

**描述**：上传文档到知识库。支持 multipart/form-data 上传。

**请求格式**：`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | 是 | 上传的文件 |

**支持的文件类型**：PDF, TXT, MD, CSV, DOCX

**业务逻辑**：

1. 校验知识库归属
2. 检测文件类型（通过扩展名）
   - 不支持的类型 → 400 `UNSUPPORTED_FILE_TYPE`
3. 校验文件大小
   - 超出限制 → 400 `FILE_TOO_LARGE`
4. 保存文件到本地存储：`{upload_base_dir}/{kb_id}/{uuid}_{filename}`
5. 创建 `KnowledgeDocument` 记录：`status=pending`
6. 更新知识库 `document_count` + 1、`total_size` + file_size
7. 提交 Celery 任务 `process_document_task.delay(str(document.id))`
8. 返回文档信息

**响应体**：

```json
{
    "code": 0,
    "message": "文档上传成功，正在处理中",
    "data": {
        "id": "uuid",
        "filename": "report.pdf",
        "file_size": 1048576,
        "file_type": "pdf",
        "status": "pending",
        "created_at": "..."
    }
}
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 400 | `UNSUPPORTED_FILE_TYPE` | 不支持的文件类型 |
| 400 | `FILE_TOO_LARGE` | 文件超出大小限制 |
| 400 | `EMPTY_FILE` | 文件为空 |
| 404 | `KNOWLEDGE_BASE_NOT_FOUND` | 知识库不存在 |

---

#### 8.2.3 删除文档

**`DELETE /api/knowledge/:id/documents/:doc_id`**

**描述**：删除文档及其所有 chunks，同时删除物理文件。

**业务逻辑**：

1. 校验知识库和文档归属
2. 记录文件路径和 chunk 数量
3. 删除文档记录（`cascade` 自动删除 chunks）
4. 删除物理文件
5. 更新知识库统计：`document_count` - 1、`total_size` - file_size
6. 返回删除结果

**响应体**：

```json
{
    "code": 0,
    "message": "文档已删除",
    "data": {
        "document_id": "uuid",
        "deleted_chunks": 25
    }
}
```

---

#### 8.2.4 重新处理文档

**`POST /api/knowledge/:id/documents/:doc_id/reprocess`**

**描述**：重新处理失败的文档（或强制重新处理已就绪的文档）。

**业务逻辑**：

1. 校验文档归属
2. 删除旧的 chunks
3. 重置文档状态为 `pending`，清除 `error_message`
4. 重新提交 Celery 任务
5. 返回文档信息

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `DOCUMENT_NOT_FOUND` | 文档不存在 |
| 400 | `DOCUMENT_PROCESSING` | 文档正在处理中，无法重新处理 |

**响应体**：

```json
{
    "code": 0,
    "message": "文档已重新提交处理",
    "data": { "id": "uuid", "status": "pending" }
}
```

---

#### 8.2.5 查询文档处理状态

**`GET /api/knowledge/:id/documents/:doc_id/status`**

**描述**：查询文档的处理状态（用于前端轮询）。

**业务逻辑**：查询文档记录，返回状态相关字段。

**响应体**：`KnowledgeDocumentStatusResponse`

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "id": "uuid",
        "status": "processing",
        "chunk_count": 0,
        "token_count": 0,
        "error_message": null,
        "processing_started_at": "2026-07-13T10:05:00Z",
        "processing_completed_at": null
    }
}
```

---

### 8.3 检索 API

#### 8.3.1 检索测试

**`POST /api/knowledge/:id/search`**

**描述**：在指定知识库中执行向量检索，返回最相似的 Top-K 文本块。

**请求体**：

```json
{
    "query": "如何配置 Agent 的系统提示词？",
    "top_k": 5
}
```

**业务逻辑**：

1. 校验知识库归属
2. 调用 `VectorSearchService.search()`
3. 返回检索结果

**响应体**：`SearchResponse`

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "query": "如何配置 Agent 的系统提示词？",
        "total": 3,
        "results": [
            {
                "chunk_id": "uuid",
                "content": "在 Agent 配置页面中，系统提示词（System Prompt）用于定义 Agent 的角色和行为规范...",
                "chunk_index": 2,
                "token_count": 456,
                "document_id": "uuid",
                "filename": "agent_guide.pdf",
                "score": 0.892341
            }
        ]
    }
}
```

**错误场景**：

| HTTP 状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 404 | `KNOWLEDGE_BASE_NOT_FOUND` | 知识库不存在 |
| 400 | `NO_READY_DOCUMENTS` | 知识库中没有已就绪的文档 |

---

## 9. Service 层完整定义

### 9.1 `app/services/knowledge_service.py`

```python
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
        await db.delete(kb)  # cascade 自动删除 documents 和 chunks
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
        await db.delete(doc)

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
```

---

## 10. 路由层实现

### 10.1 `app/api/v1/knowledge.py`

```python
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
```

### 10.2 路由注册

```python
# app/api/router.py — Phase 3 修改

api_router.include_router(
    knowledge.router,
    prefix="/knowledge",
    tags=["Knowledge"],
)
```

---

## 11. 配置变更

### 11.1 `.env` 新增配置项

```env
# ---- Phase 3: Knowledge Base ----
UPLOAD_BASE_DIR=./uploads
DEFAULT_EMBEDDING_API_KEY=sk-xxx
DEFAULT_EMBEDDING_BASE_URL=https://api.openai.com/v1
DEFAULT_EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_BATCH_SIZE=20
EMBEDDING_REQUEST_TIMEOUT=60
```

### 11.2 `app/core/config.py` 新增字段

```python
class Settings(BaseSettings):
    # ... Phase 0/1/2 已有字段 ...

    # Phase 3: Knowledge Base
    upload_base_dir: str = "./uploads"
    default_embedding_api_key: str = ""
    default_embedding_base_url: str = "https://api.openai.com/v1"
    default_embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 20
    embedding_request_timeout: int = 60
```

---

## 12. 目录结构变更（Phase 3 新增/修改的文件）

```
app/
├── core/
│   ├── config.py              # 【修改】新增 Phase 3 配置字段
│   ├── celery_app.py          # 【新增】Celery 应用配置
│   └── storage.py             # 【新增】文件存储管理
├── models/
│   ├── knowledge.py           # 【修改】增强知识库模型
│   └── enums.py               # 【修改】DocumentStatus 新增 pending，新增 FileType
├── schemas/
│   └── knowledge.py           # 【修改】完整 Schema 定义
├── services/
│   ├── knowledge_service.py   # 【新增】知识库 + 文档 CRUD 服务
│   ├── text_extractor.py      # 【新增】文本提取器
│   ├── text_chunker.py        # 【新增】文本分块器
│   ├── embedding_service.py   # 【新增】Embedding API 调用服务
│   ├── document_processor.py  # 【新增】Pipeline 主处理器
│   └── vector_search_service.py  # 【新增】向量检索服务
├── tasks/
│   ├── __init__.py            # 【新增】
│   └── knowledge_tasks.py     # 【新增】Celery 任务定义
├── api/
│   ├── router.py              # 【修改】注册 knowledge 路由
│   └── v1/
│       └── knowledge.py       # 【修改】从空骨架到完整实现
└── tests/
    ├── test_knowledge.py      # 【新增】
    ├── test_text_extractor.py # 【新增】
    ├── test_text_chunker.py   # 【新增】
    └── test_vector_search.py  # 【新增】

uploads/                        # 【新增】上传文件存储目录（git-ignored）
```

---

## 13. 错误码汇总

### 13.1 知识库相关

| 错误码 | HTTP 状态码 | 说明 |
|--------|-----------|------|
| `KNOWLEDGE_BASE_NOT_FOUND` | 404 | 知识库不存在 |
| `FORBIDDEN` | 403 | 无权操作此知识库 |
| `INVALID_EMBEDDING_MODEL` | 400 | 不支持的 Embedding 模型 |
| `INVALID_CHUNK_CONFIG` | 400 | 分块配置无效（overlap >= size） |

### 13.2 文档相关

| 错误码 | HTTP 状态码 | 说明 |
|--------|-----------|------|
| `DOCUMENT_NOT_FOUND` | 404 | 文档不存在 |
| `UNSUPPORTED_FILE_TYPE` | 400 | 不支持的文件类型 |
| `FILE_TOO_LARGE` | 400 | 文件超出大小限制 |
| `EMPTY_FILE` | 400 | 文件为空 |
| `DOCUMENT_PROCESSING` | 400 | 文档正在处理中 |
| `NO_FILENAME` | 400 | 未提供文件名 |
| `NO_READY_DOCUMENTS` | 400 | 知识库中没有已就绪的文档 |

### 13.3 Embedding / 检索相关

| 错误码 | HTTP 状态码 | 说明 |
|--------|-----------|------|
| `EMBEDDING_AUTH_FAILED` | 400 | Embedding API 认证失败 |
| `EMBEDDING_RATE_LIMITED` | 429 | Embedding API 频率超限 |
| `EMBEDDING_API_ERROR` | 502 | Embedding API 返回错误 |
| `EMBEDDING_TIMEOUT` | 504 | Embedding API 请求超时 |
| `EMBEDDING_NETWORK_ERROR` | 502 | Embedding API 网络错误 |

---

## 14. 与 Phase 0/1/2 的衔接

### 14.1 数据库模型变更

Phase 0 定义了 KnowledgeBase、KnowledgeDocument、KnowledgeChunk 的基础模型。Phase 3 在此基础上增强：
- 新增统计字段、处理状态字段、token 统计字段
- 枚举扩展：DocumentStatus 新增 pending
- 新增 embedding_dimensions 字段

### 14.2 路由注册

Phase 0 已注册空骨架路由 `app/api/v1/knowledge.py`。Phase 3 将空骨架替换为完整实现，路由前缀保持 `/api/knowledge`。

### 14.3 依赖注入复用

```python
from app.api.deps import get_current_user, CurrentUser, DBSession
```

### 14.4 响应格式统一

遵循 Phase 1 定义的统一响应格式。

### 14.5 复用模型管理模块

EmbeddingService 复用 Phase 2 的 ModelProvider 和 LLMModel 表来获取用户的 API Key 和 base_url：
- 查询用户已配置的供应商中是否有匹配的 Embedding 模型
- 如果用户未配置，使用系统默认的 `.env` 配置

### 14.6 Agent-KnowledgeBase 关联表激活

Phase 2 已创建的 `agent_knowledge_bases` 关联表现在被激活：
- `AgentKnowledgeBase` 模型的 relationship 可以正常使用
- Agent 配置中可通过此关联表关联知识库
- 后续 Phase（如工作流执行）可通过此表获取 Agent 关联的知识库进行 RAG 检索

### 14.7 加密模块复用

```python
from app.core.encryption import decrypt_value
```

EmbeddingService 使用 Phase 2 的 `decrypt_value` 来解密用户的 API Key。

### 14.8 异步引擎复用

```python
from app.core.database import async_session_factory
```

Celery Worker 中通过 `async_session_factory` 创建独立的数据库 session，不复用 FastAPI 的 request-scoped session。

---

## 15. 依赖和配置

### 15.1 新增 Python 依赖

```
# requirements.txt — Phase 3 新增
celery>=5.3.0
PyMuPDF>=1.24.0
python-docx>=1.1.0
tiktoken>=0.7.0
```

### 15.2 Docker Compose 变更

无需新增容器。Celery Worker 使用同一个 Redis 实例作为消息代理。

```yaml
# docker-compose.yml — Phase 3 新增 service
services:
  celery-worker:
    build: .
    command: celery -A app.core.celery_app worker --loglevel=info --queues=knowledge --concurrency=4
    volumes:
      - .:/app
      - upload_data:/app/uploads
    depends_on:
      - db
      - redis
    environment:
      - DATABASE_URL=postgresql+asyncpg://...
      - REDIS_URL=redis://redis:6379/0

volumes:
  upload_data:  # 文件上传持久化卷
```

---

## 16. 测试用例

### 16.1 `tests/test_text_chunker.py`

```python
import pytest
from app.services.text_chunker import TextChunker


class TestTextChunker:

    def test_basic_chunking(self):
        """基本分块：短文本不拆分"""
        chunker = TextChunker(chunk_size=512, chunk_overlap=50)
        text = "这是一段短文本。" * 10
        chunks = chunker.chunk_text(text)
        assert len(chunks) >= 1
        assert all(c.content.strip() for c in chunks)

    def test_long_text_chunking(self):
        """长文本分块：超过 chunk_size 时正确拆分"""
        chunker = TextChunker(chunk_size=100, chunk_overlap=10)
        text = "这是一段很长的文本。" * 500  # 约 5000+ tokens
        chunks = chunker.chunk_text(text)
        assert len(chunks) > 1
        # 验证重叠
        for i in range(1, len(chunks)):
            assert chunks[i].chunk_index == i

    def test_empty_text(self):
        """空文本返回空列表"""
        chunker = TextChunker()
        chunks = chunker.chunk_text("")
        assert chunks == []

    def test_token_count(self):
        """验证 token 计数正确"""
        chunker = TextChunker(chunk_size=512)
        text = "Hello world, this is a test." * 100
        chunks = chunker.chunk_text(text)
        total_tokens = sum(c.token_count for c in chunks)
        direct_count = chunker.count_tokens(text)
        # 由于重叠，总 token 数可能大于直接计数
        assert total_tokens >= direct_count

    def test_overlap_invalid_config(self):
        """overlap >= size 时抛出 ValueError"""
        with pytest.raises(ValueError):
            TextChunker(chunk_size=100, chunk_overlap=100)

    def test_paragraph_boundary(self):
        """尽量在段落边界分块"""
        chunker = TextChunker(chunk_size=50, chunk_overlap=5)
        text = "\n\n".join([f"段落 {i}: " + "内容" * 20 for i in range(10)])
        chunks = chunker.chunk_text(text)
        assert len(chunks) >= 1


class TestTextChunkerCountTokens:

    def test_count_tokens_chinese(self):
        """中文 token 计数"""
        chunker = TextChunker()
        count = chunker.count_tokens("你好世界")
        assert count > 0

    def test_count_tokens_english(self):
        """英文 token 计数"""
        chunker = TextChunker()
        count = chunker.count_tokens("Hello world")
        assert count > 0
```

### 16.2 `tests/test_text_extractor.py`

```python
import pytest
import tempfile
from pathlib import Path

from app.services.text_extractor import (
    detect_file_type,
    extract_text,
    validate_file_size,
)


class TestDetectFileType:

    def test_pdf(self):
        assert detect_file_type("report.pdf") == "pdf"

    def test_txt(self):
        assert detect_file_type("notes.txt") == "txt"

    def test_markdown(self):
        assert detect_file_type("readme.md") == "md"
        assert detect_file_type("readme.markdown") == "md"

    def test_csv(self):
        assert detect_file_type("data.csv") == "csv"

    def test_docx(self):
        assert detect_file_type("doc.docx") == "docx"

    def test_unsupported(self):
        assert detect_file_type("image.png") is None
        assert detect_file_type("archive.zip") is None


class TestValidateFileSize:

    def test_valid_size(self):
        validate_file_size(1024, "pdf")  # 不抛异常

    def test_too_large(self):
        with pytest.raises(ValueError):
            validate_file_size(100 * 1024 * 1024, "pdf")  # 100MB > 50MB limit


class TestExtractText:

    def test_extract_txt(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
            f.write("Hello, World!\n这是测试文本。")
            f.flush()
            text = extract_text(f.name, "txt")
            assert "Hello, World!" in text
            assert "测试文本" in text

    def test_extract_csv(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8") as f:
            f.write("name,age,city\nAlice,30,NYC\nBob,25,LA")
            f.flush()
            text = extract_text(f.name, "csv")
            assert "Alice" in text
            assert "name" in text

    def test_unsupported_type(self):
        with pytest.raises(ValueError):
            extract_text("/tmp/test.xyz", "xyz")
```

### 16.3 `tests/test_knowledge.py`

```python
import pytest
import io


@pytest.mark.asyncio
class TestKnowledgeBases:

    async def test_create_kb(self, client, auth_headers):
        """创建知识库"""
        response = await client.post("/api/knowledge", json={
            "name": "测试知识库",
            "description": "用于测试",
            "chunk_size": 512,
            "chunk_overlap": 50,
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "测试知识库"
        assert data["chunk_size"] == 512

    async def test_list_kb_empty(self, client, auth_headers):
        """空知识库列表"""
        response = await client.get("/api/knowledge", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 0

    async def test_get_kb_not_found(self, client, auth_headers):
        """获取不存在的知识库"""
        response = await client.get(
            "/api/knowledge/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_delete_kb(self, client, auth_headers):
        """删除知识库"""
        # 先创建
        create_resp = await client.post("/api/knowledge", json={
            "name": "待删除",
        }, headers=auth_headers)
        kb_id = create_resp.json()["data"]["id"]

        # 删除
        response = await client.delete(f"/api/knowledge/{kb_id}", headers=auth_headers)
        assert response.status_code == 200

    async def test_update_config(self, client, auth_headers):
        """更新分块配置"""
        create_resp = await client.post("/api/knowledge", json={
            "name": "配置测试",
        }, headers=auth_headers)
        kb_id = create_resp.json()["data"]["id"]

        response = await client.put(f"/api/knowledge/{kb_id}/config", json={
            "chunk_size": 1024,
            "chunk_overlap": 100,
        }, headers=auth_headers)
        assert response.status_code == 200


@pytest.mark.asyncio
class TestDocuments:

    async def test_upload_txt_document(self, client, auth_headers):
        """上传 TXT 文档"""
        # 创建知识库
        kb_resp = await client.post("/api/knowledge", json={
            "name": "文档测试",
        }, headers=auth_headers)
        kb_id = kb_resp.json()["data"]["id"]

        # 上传文档
        file_content = b"This is test content.\nSecond line."
        response = await client.post(
            f"/api/knowledge/{kb_id}/documents",
            files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "pending"
        assert data["file_type"] == "txt"

    async def test_upload_unsupported_type(self, client, auth_headers):
        """上传不支持的文件类型"""
        kb_resp = await client.post("/api/knowledge", json={
            "name": "类型测试",
        }, headers=auth_headers)
        kb_id = kb_resp.json()["data"]["id"]

        response = await client.post(
            f"/api/knowledge/{kb_id}/documents",
            files={"file": ("test.png", io.BytesIO(b"fake"), "image/png")},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    async def test_document_list(self, client, auth_headers):
        """获取文档列表"""
        kb_resp = await client.post("/api/knowledge", json={
            "name": "列表测试",
        }, headers=auth_headers)
        kb_id = kb_resp.json()["data"]["id"]

        response = await client.get(
            f"/api/knowledge/{kb_id}/documents",
            headers=auth_headers,
        )
        assert response.status_code == 200
```

### 16.4 `tests/test_vector_search.py`

```python
import pytest


@pytest.mark.asyncio
class TestVectorSearch:

    async def test_search_empty_kb(self, client, auth_headers):
        """检索空知识库"""
        kb_resp = await client.post("/api/knowledge", json={
            "name": "检索测试",
        }, headers=auth_headers)
        kb_id = kb_resp.json()["data"]["id"]

        response = await client.post(
            f"/api/knowledge/{kb_id}/search",
            json={"query": "测试查询", "top_k": 5},
            headers=auth_headers,
        )
        # 空知识库可能返回空结果或 NO_READY_DOCUMENTS 错误
        assert response.status_code in (200, 400)

    async def test_search_after_document(self, client, auth_headers):
        """上传文档后检索（需要真实的 Embedding API）"""
        # 这是一个集成测试，需要配置有效的 Embedding API Key
        # 在 CI 中应标记为 @pytest.mark.integration
        pass
```

---

## 17. 给 Cursor 的额外说明

### 17.1 实现顺序建议

请按照以下顺序实现 Phase 3：

1. **数据库模型变更**（`app/models/knowledge.py` + `enums.py`）→ 运行 Alembic 迁移
2. **配置变更**（`app/core/config.py` + `.env`）
3. **文件存储模块**（`app/core/storage.py`）
4. **Celery 配置**（`app/core/celery_app.py`）
5. **文本提取器**（`app/services/text_extractor.py`）+ 单元测试
6. **文本分块器**（`app/services/text_chunker.py`）+ 单元测试
7. **Embedding 服务**（`app/services/embedding_service.py`）
8. **Pipeline 处理器**（`app/services/document_processor.py`）
9. **Celery 任务**（`app/tasks/knowledge_tasks.py`）
10. **知识库 Service**（`app/services/knowledge_service.py`）
11. **向量检索 Service**（`app/services/vector_search_service.py`）
12. **Pydantic Schemas**（`app/schemas/knowledge.py`）
13. **路由层**（`app/api/v1/knowledge.py`）
14. **集成测试**

### 17.2 关键注意事项

1. **Celery + AsyncIO**：Celery Worker 是同步的，但我们的数据库操作是异步的（async SQLAlchemy）。解决方案是在 Celery 任务中创建新的事件循环来运行异步代码（见 `knowledge_tasks.py` 中的实现）。

2. **pgvector 类型**：`Vector(1536)` 类型需要 `pgvector` Python 包和 PostgreSQL `vector` 扩展。确保 Docker 镜像使用 `pgvector/pgvector:pg16` 镜像。

3. **文件上传大小**：FastAPI 默认没有文件大小限制，但需要在 `UploadFile` 处理时添加限制。建议在中间件或 Service 层校验。

4. **Embedding 批处理**：每批最多 20 个文本（可通过 `EMBEDDING_BATCH_SIZE` 配置）。大批量时注意 API 限流。

5. **事务管理**：Pipeline 中的数据库操作在一个事务内完成。如果中间步骤失败，整个事务回滚。但 Celery 任务中需要手动管理 session 和事务。

6. **向量索引创建时机**：HNSW 索引应在知识库有大量数据后再创建（或在 Alembic 迁移中预创建）。少量数据时暴力搜索也足够快。

7. **文本提取编码**：PDF 和 DOCX 通常使用 UTF-8，但 TXT/CSV 可能是 GBK 等中文编码。`_extract_txt` 和 `_extract_csv` 方法已实现多编码尝试。

8. **Chunk 重叠**：重叠的目的是避免在切分边界处丢失关键信息。`_add_overlap` 方法确保后一个块的开头包含前一个块末尾的部分内容。

9. **知识库删除时的文件清理**：删除知识库时需要遍历所有文档的物理文件并删除。这应该在数据库记录删除成功后执行，避免数据库回滚但文件已删的不一致状态。

10. **分块配置变更**：更新 `chunk_size` 或 `chunk_overlap` 后，已有的 chunks 不再有效。需要将相关文档标记为 `pending` 并删除旧 chunks，由 Celery 重新处理。

### 17.3 性能考虑

- **批量 INSERT**：大量 chunks 写入时，可以考虑使用 `executemany` 或 `bulk_insert_mappings` 提高性能
- **HNSW 索引构建**：首次创建索引时可能较慢（取决于数据量），建议在文档数量较少时预创建
- **Embedding API 延迟**：单个请求的延迟约 200-500ms，批量处理 20 个文本约 1-2 秒。对于大文档（100+ chunks），总 Embedding 时间可能需要 10-30 秒
- **内存管理**：Celery Worker 设置 `worker_max_tasks_per_child=50` 防止内存泄漏。大 PDF 的文本提取可能占用较多内存

### 17.4 后续扩展预留

- **多路召回**：当前仅使用向量检索，后续可添加 BM25 关键词检索，融合排序
- **Rerank**：检索后使用 Rerank 模型重新排序（如 Cohere Rerank）
- **混合搜索**：向量搜索 + 全文搜索（PostgreSQL `tsvector`）
- **增量索引**：对于新增文档，只索引新增的 chunks，不影响已有索引
- **文档解析增强**：支持更多格式（HTML、Excel、PPT 等）
- **异步状态推送**：使用 WebSocket 替代轮询，实时推送文档处理进度

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
