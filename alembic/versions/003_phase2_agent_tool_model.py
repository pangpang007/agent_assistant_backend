"""Phase 2: agent, tool, model management schema changes."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_phase2_agent_tool_model"
down_revision: Union[str, None] = "002_phase1_user_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- llm_models (must exist before agents.model_id FK) ----
    op.create_table(
        "llm_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column(
            "input_price",
            sa.Numeric(precision=10, scale=6),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "output_price",
            sa.Numeric(precision=10, scale=6),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "is_enabled", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["model_providers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_models_provider_id", "llm_models", ["provider_id"])

    # ---- agents ----
    op.alter_column("agents", "user_id", existing_type=postgresql.UUID(), nullable=True)
    op.drop_column("agents", "model_provider")
    op.drop_column("agents", "model_name")
    op.drop_column("agents", "tools")
    op.drop_column("agents", "knowledge_base_ids")
    op.add_column(
        "agents",
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_agents_model_id", "agents", ["model_id"])
    op.create_foreign_key(
        "fk_agents_model_id_llm_models",
        "agents",
        "llm_models",
        ["model_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---- tools ----
    op.add_column(
        "tools",
        sa.Column(
            "tool_type", sa.String(length=20), nullable=False, server_default="custom"
        ),
    )
    op.add_column(
        "tools", sa.Column("openapi_spec", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "tools", sa.Column("api_url", sa.String(length=2048), nullable=True)
    )
    op.add_column(
        "tools",
        sa.Column(
            "auth_type", sa.String(length=20), nullable=False, server_default="none"
        ),
    )
    op.add_column(
        "tools", sa.Column("auth_config", postgresql.JSONB(), nullable=True)
    )
    op.execute("UPDATE tools SET tool_type = 'custom' WHERE tool_type IS NULL")
    op.drop_column("tools", "type")
    op.drop_column("tools", "config")

    # ---- model_providers ----
    op.add_column(
        "model_providers",
        sa.Column(
            "provider_type",
            sa.String(length=20),
            nullable=False,
            server_default="custom",
        ),
    )
    op.alter_column(
        "model_providers",
        "enabled",
        new_column_name="is_enabled",
        existing_type=sa.Boolean(),
    )
    op.drop_column("model_providers", "is_default")

    # ---- model_usages ----
    op.add_column(
        "model_usages",
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "model_usages",
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_model_usages_provider_id", "model_usages", ["provider_id"])
    op.create_index("ix_model_usages_model_id", "model_usages", ["model_id"])
    op.create_foreign_key(
        "fk_model_usages_provider_id",
        "model_usages",
        "model_providers",
        ["provider_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_model_usages_model_id",
        "model_usages",
        "llm_models",
        ["model_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---- association tables ----
    op.create_table(
        "agent_tools",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tool_id"], ["tools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "tool_id", name="uq_agent_tool"),
    )
    op.create_index("ix_agent_tools_agent_id", "agent_tools", ["agent_id"])
    op.create_index("ix_agent_tools_tool_id", "agent_tools", ["tool_id"])

    op.create_table(
        "agent_knowledge_bases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "knowledge_base_id", name="uq_agent_kb"),
    )
    op.create_index(
        "ix_agent_knowledge_bases_agent_id", "agent_knowledge_bases", ["agent_id"]
    )
    op.create_index(
        "ix_agent_knowledge_bases_knowledge_base_id",
        "agent_knowledge_bases",
        ["knowledge_base_id"],
    )


def downgrade() -> None:
    op.drop_table("agent_knowledge_bases")
    op.drop_table("agent_tools")

    op.drop_constraint("fk_model_usages_model_id", "model_usages", type_="foreignkey")
    op.drop_constraint(
        "fk_model_usages_provider_id", "model_usages", type_="foreignkey"
    )
    op.drop_index("ix_model_usages_model_id", "model_usages")
    op.drop_index("ix_model_usages_provider_id", "model_usages")
    op.drop_column("model_usages", "model_id")
    op.drop_column("model_usages", "provider_id")

    op.add_column(
        "model_providers",
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.alter_column(
        "model_providers",
        "is_enabled",
        new_column_name="enabled",
        existing_type=sa.Boolean(),
    )
    op.drop_column("model_providers", "provider_type")

    op.add_column("tools", sa.Column("config", postgresql.JSONB(), nullable=True))
    op.add_column(
        "tools",
        sa.Column("type", sa.String(length=20), nullable=False, server_default="custom"),
    )
    op.drop_column("tools", "auth_config")
    op.drop_column("tools", "auth_type")
    op.drop_column("tools", "api_url")
    op.drop_column("tools", "openapi_spec")
    op.drop_column("tools", "tool_type")

    op.drop_constraint("fk_agents_model_id_llm_models", "agents", type_="foreignkey")
    op.drop_index("ix_agents_model_id", "agents")
    op.drop_column("agents", "model_id")
    op.add_column(
        "agents", sa.Column("knowledge_base_ids", postgresql.JSONB(), nullable=True)
    )
    op.add_column("agents", sa.Column("tools", postgresql.JSONB(), nullable=True))
    op.add_column(
        "agents", sa.Column("model_name", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "agents", sa.Column("model_provider", sa.String(length=100), nullable=True)
    )
    op.alter_column("agents", "user_id", existing_type=postgresql.UUID(), nullable=False)

    op.drop_index("ix_llm_models_provider_id", "llm_models")
    op.drop_table("llm_models")
