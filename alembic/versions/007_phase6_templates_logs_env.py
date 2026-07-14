"""Phase 6: templates enrichment, log search, env unique constraint.

Revision ID: 007_phase6_templates_logs_env
Revises: 006_phase5_execution_indexes
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007_phase6_templates_logs_env"
down_revision: Union[str, None] = "006_phase5_execution_indexes"
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


def _fk_names(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {fk["name"] for fk in inspector.get_foreign_keys(table) if fk.get("name")}


def upgrade() -> None:
    cols = _column_names("templates")

    if "user_id" not in cols:
        op.add_column(
            "templates",
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    if "nodes_data" not in cols:
        op.add_column(
            "templates",
            sa.Column(
                "nodes_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True
            ),
        )
    if "edges_data" not in cols:
        op.add_column(
            "templates",
            sa.Column(
                "edges_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True
            ),
        )
    if "is_preset" not in cols:
        op.add_column(
            "templates",
            sa.Column(
                "is_preset",
                sa.Boolean(),
                server_default="false",
                nullable=False,
            ),
        )

    indexes = _index_names("templates")
    if "ix_templates_user_id" not in indexes:
        op.create_index("ix_templates_user_id", "templates", ["user_id"])

    fks = _fk_names("templates")
    if "fk_templates_user_id_users" not in fks:
        # recreate may be needed after fresh create_all with different FK name
        has_user_fk = any("user" in (name or "") for name in fks)
        if not has_user_fk:
            op.create_foreign_key(
                "fk_templates_user_id_users",
                "templates",
                "users",
                ["user_id"],
                ["id"],
                ondelete="SET NULL",
            )

    # Drop unique on workflow_id if present
    op.execute("ALTER TABLE templates DROP CONSTRAINT IF EXISTS templates_workflow_id_key")
    op.execute(
        "ALTER TABLE templates DROP CONSTRAINT IF EXISTS uq_templates_workflow_id"
    )
    op.execute("DROP INDEX IF EXISTS templates_workflow_id_key")

    # Make workflow_id nullable
    op.execute("ALTER TABLE templates ALTER COLUMN workflow_id DROP NOT NULL")

    # Ensure FK is SET NULL
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys("templates"):
        referred = fk.get("referred_table")
        constrained = fk.get("constrained_columns") or []
        if referred == "workflows" and "workflow_id" in constrained:
            # Drop and recreate with SET NULL if needed
            ondelete = (fk.get("options") or {}).get("ondelete")
            if ondelete != "SET NULL" and fk.get("name"):
                op.drop_constraint(fk["name"], "templates", type_="foreignkey")
                op.create_foreign_key(
                    "fk_templates_workflow_id_workflows",
                    "templates",
                    "workflows",
                    ["workflow_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
                break
    else:
        fks = _fk_names("templates")
        if "fk_templates_workflow_id_workflows" not in fks and not any(
            "workflow" in (n or "") for n in fks
        ):
            op.create_foreign_key(
                "fk_templates_workflow_id_workflows",
                "templates",
                "workflows",
                ["workflow_id"],
                ["id"],
                ondelete="SET NULL",
            )

    indexes = _index_names("templates")
    if "ix_templates_workflow_id" not in indexes:
        op.create_index("ix_templates_workflow_id", "templates", ["workflow_id"])
    if "ix_templates_category_preset" not in indexes:
        op.create_index(
            "ix_templates_category_preset", "templates", ["category", "is_preset"]
        )
    if "ix_templates_is_preset" not in indexes:
        op.create_index("ix_templates_is_preset", "templates", ["is_preset"])

    # env_variables unique (may already exist from 001)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_env_variables_user_key'
            ) AND NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'uq_env_variables_user_key'
            ) THEN
                CREATE UNIQUE INDEX uq_env_variables_user_key
                ON env_variables (user_id, key);
            END IF;
        END $$;
        """
    )

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_logs_message_trgm "
        "ON logs USING gin (message gin_trgm_ops)"
    )

    # Skip if already in 006
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_executions_workflow_status "
        "ON executions (workflow_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_executions_started_at "
        "ON executions (started_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_executions_started_at")
    op.execute("DROP INDEX IF EXISTS ix_executions_workflow_status")
    op.execute("DROP INDEX IF EXISTS ix_logs_message_trgm")

    op.execute("DROP INDEX IF EXISTS ix_templates_is_preset")
    op.execute("DROP INDEX IF EXISTS ix_templates_category_preset")

    cols = _column_names("templates")
    if "is_preset" in cols:
        op.drop_column("templates", "is_preset")
    if "edges_data" in cols:
        op.drop_column("templates", "edges_data")
    if "nodes_data" in cols:
        op.drop_column("templates", "nodes_data")
    if "user_id" in cols:
        fks = _fk_names("templates")
        if "fk_templates_user_id_users" in fks:
            op.drop_constraint(
                "fk_templates_user_id_users", "templates", type_="foreignkey"
            )
        op.execute("DROP INDEX IF EXISTS ix_templates_user_id")
        op.drop_column("templates", "user_id")
