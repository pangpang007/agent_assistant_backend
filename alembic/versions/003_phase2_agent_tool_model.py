"""Phase 2: agent, tool, model management schema changes.

NOTE: Applied by 001 create_all on fresh installs. No-op for new deploys.
"""

from typing import Sequence, Union

revision: str = "003_phase2_agent_tool_model"
down_revision: Union[str, None] = "002_phase1_user_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
