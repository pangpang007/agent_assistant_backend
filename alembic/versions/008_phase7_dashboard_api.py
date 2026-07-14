"""Phase 7: execution source, workflow API stats, performance indexes.

Revision ID: 008_phase7_dashboard_api
Revises: 007_phase6_templates_logs_env
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008_phase7_dashboard_api"
down_revision: Union[str, None] = "007_phase6_templates_logs_env"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns(table)}


def _index_names(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade() -> None:
    # ---- executions: source + api_caller_workflow_id ----
    exec_cols = _column_names("executions")
    if "source" not in exec_cols:
        op.add_column(
            "executions",
            sa.Column(
                "source",
                sa.String(20),
                nullable=False,
                server_default="web",
            ),
        )
    if "api_caller_workflow_id" not in exec_cols:
        op.add_column(
            "executions",
            sa.Column(
                "api_caller_workflow_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_executions_source ON executions (source)"
    )
    # No executions.user_id — index by workflow_id + started_at for dashboard JOIN
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_executions_workflow_started "
        "ON executions (workflow_id, started_at DESC)"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_executions_workflow_month
        ON executions (workflow_id, started_at DESC)
        WHERE status IN ('success', 'failed')
        """
    )

    # ---- workflows: API stats + published_api_key String(64) ----
    wf_cols = _column_names("workflows")
    if "api_call_count" not in wf_cols:
        op.add_column(
            "workflows",
            sa.Column(
                "api_call_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
    if "api_total_duration_ms" not in wf_cols:
        op.add_column(
            "workflows",
            sa.Column(
                "api_total_duration_ms",
                sa.BigInteger(),
                nullable=False,
                server_default="0",
            ),
        )
    if "api_success_count" not in wf_cols:
        op.add_column(
            "workflows",
            sa.Column(
                "api_success_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
    if "api_is_active" not in wf_cols:
        op.add_column(
            "workflows",
            sa.Column(
                "api_is_active",
                sa.Boolean(),
                nullable=False,
                server_default="true",
            ),
        )

    # Convert published_api_key UUID → VARCHAR(64) (drop legacy UUID keys)
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    col_info = {
        c["name"]: c for c in inspector.get_columns("workflows")
    }
    pak = col_info.get("published_api_key")
    if pak is not None:
        col_type = pak["type"]
        type_name = type(col_type).__name__.lower()
        if "uuid" in type_name or getattr(col_type, "as_uuid", False):
            op.execute(
                "UPDATE workflows SET published_api_key = NULL "
                "WHERE published_api_key IS NOT NULL"
            )
            # Drop unique constraint/index on UUID column if present
            op.execute(
                "ALTER TABLE workflows DROP CONSTRAINT IF EXISTS "
                "workflows_published_api_key_key"
            )
            op.execute("DROP INDEX IF EXISTS workflows_published_api_key_key")
            op.execute("DROP INDEX IF EXISTS ix_workflows_published_api_key")
            op.execute(
                "ALTER TABLE workflows "
                "ALTER COLUMN published_api_key TYPE VARCHAR(64) "
                "USING NULL"
            )
            op.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_workflows_published_api_key "
                "ON workflows (published_api_key) "
                "WHERE published_api_key IS NOT NULL"
            )

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Search / dashboard indexes (idempotent)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflows_name_trgm "
        "ON workflows USING gin (name gin_trgm_ops)"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflows_desc_trgm
        ON workflows USING gin (description gin_trgm_ops)
        WHERE description IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agents_name_trgm "
        "ON agents USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_bases_name_trgm "
        "ON knowledge_bases USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_templates_name_trgm "
        "ON templates USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_model_usages_user_date "
        "ON model_usages (user_id, date DESC)"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflows_published
        ON workflows (user_id)
        WHERE is_published_api = true
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_workflows_published")
    op.execute("DROP INDEX IF EXISTS ix_model_usages_user_date")
    op.execute("DROP INDEX IF EXISTS ix_templates_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_bases_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_agents_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_workflows_desc_trgm")
    op.execute("DROP INDEX IF EXISTS ix_workflows_name_trgm")

    wf_cols = _column_names("workflows")
    if "api_is_active" in wf_cols:
        op.drop_column("workflows", "api_is_active")
    if "api_success_count" in wf_cols:
        op.drop_column("workflows", "api_success_count")
    if "api_total_duration_ms" in wf_cols:
        op.drop_column("workflows", "api_total_duration_ms")
    if "api_call_count" in wf_cols:
        op.drop_column("workflows", "api_call_count")

    # Revert published_api_key to UUID (null out string keys first)
    op.execute("UPDATE workflows SET published_api_key = NULL")
    op.execute("DROP INDEX IF EXISTS uq_workflows_published_api_key")
    op.execute(
        "ALTER TABLE workflows "
        "ALTER COLUMN published_api_key TYPE UUID USING NULL"
    )

    op.execute("DROP INDEX IF EXISTS ix_executions_workflow_month")
    op.execute("DROP INDEX IF EXISTS ix_executions_workflow_started")
    op.execute("DROP INDEX IF EXISTS ix_executions_source")

    exec_cols = _column_names("executions")
    if "api_caller_workflow_id" in exec_cols:
        op.drop_column("executions", "api_caller_workflow_id")
    if "source" in exec_cols:
        op.drop_column("executions", "source")
