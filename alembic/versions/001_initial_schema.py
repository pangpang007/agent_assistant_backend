"""initial_schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-07-13

"""

from typing import Sequence, Union

from alembic import op

import app.models  # noqa: F401
from app.models.base import Base

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    op.create_unique_constraint(
        "uq_env_variables_user_key", "env_variables", ["user_id", "key"]
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_hnsw "
        "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw")
    op.drop_constraint("uq_env_variables_user_key", "env_variables", type_="unique")
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
    op.execute("DROP EXTENSION IF EXISTS vector")
