"""Phase 3: knowledge base schema enhancements."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_phase3_knowledge_base"
down_revision: Union[str, None] = "003_phase2_agent_tool_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "knowledge_bases",
        sa.Column(
            "document_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("total_size", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "embedding_dimensions",
            sa.Integer(),
            nullable=False,
            server_default="1536",
        ),
    )

    op.add_column(
        "knowledge_documents",
        sa.Column("file_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "knowledge_documents", sa.Column("content", sa.Text(), nullable=True)
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        "UPDATE knowledge_documents SET file_type = 'txt' WHERE file_type IS NULL"
    )
    op.alter_column(
        "knowledge_documents", "file_type", nullable=False, existing_type=sa.String(20)
    )

    op.alter_column(
        "knowledge_documents",
        "status",
        server_default="pending",
        existing_type=sa.String(length=20),
    )

    op.add_column(
        "knowledge_chunks",
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.drop_column("knowledge_chunks", "metadata")

    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_hnsw "
        "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw")

    op.add_column(
        "knowledge_chunks",
        sa.Column("metadata", sa.dialects.postgresql.JSONB(), nullable=True),
    )
    op.drop_column("knowledge_chunks", "token_count")

    op.alter_column(
        "knowledge_documents",
        "status",
        server_default="processing",
        existing_type=sa.String(length=20),
    )
    op.drop_column("knowledge_documents", "processing_completed_at")
    op.drop_column("knowledge_documents", "processing_started_at")
    op.drop_column("knowledge_documents", "token_count")
    op.drop_column("knowledge_documents", "content")
    op.drop_column("knowledge_documents", "file_type")

    op.drop_column("knowledge_bases", "embedding_dimensions")
    op.drop_column("knowledge_bases", "total_size")
    op.drop_column("knowledge_bases", "document_count")
