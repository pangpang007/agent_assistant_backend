"""Phase 4: rename workflow nodes_json/edges_json to nodes_data/edges_data."""

from typing import Sequence, Union

from alembic import op

revision: str = "005_phase4_workflow_rename"
down_revision: Union[str, None] = "004_phase3_knowledge_base"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("workflows", "nodes_json", new_column_name="nodes_data")
    op.alter_column("workflows", "edges_json", new_column_name="edges_data")
    op.alter_column("workflow_versions", "nodes_json", new_column_name="nodes_data")
    op.alter_column("workflow_versions", "edges_json", new_column_name="edges_data")
    op.create_index(
        "ix_workflow_versions_wf_ver",
        "workflow_versions",
        ["workflow_id", "version_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_versions_wf_ver", table_name="workflow_versions")
    op.alter_column("workflow_versions", "nodes_data", new_column_name="nodes_json")
    op.alter_column("workflow_versions", "edges_data", new_column_name="edges_json")
    op.alter_column("workflows", "nodes_data", new_column_name="nodes_json")
    op.alter_column("workflows", "edges_data", new_column_name="edges_json")
