"""Phase 5: execution and log query indexes.

Revision ID: 006_phase5_execution_indexes
Revises: 005_phase4_workflow_rename
"""

from typing import Sequence, Union

from alembic import op

revision: str = "006_phase5_execution_indexes"
down_revision: Union[str, None] = "005_phase4_workflow_rename"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_executions_workflow_status "
        "ON executions (workflow_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_executions_started_at "
        "ON executions (started_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_logs_execution_node "
        "ON logs (execution_id, node_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_logs_level ON logs (level)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_logs_level")
    op.execute("DROP INDEX IF EXISTS ix_logs_execution_node")
    op.execute("DROP INDEX IF EXISTS ix_executions_started_at")
    op.execute("DROP INDEX IF EXISTS ix_executions_workflow_status")
