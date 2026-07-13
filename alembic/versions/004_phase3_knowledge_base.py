"""Phase 3: knowledge base schema enhancements.

NOTE: Applied by 001 create_all on fresh installs. No-op for new deploys.
"""

from typing import Sequence, Union

revision: str = "004_phase3_knowledge_base"
down_revision: Union[str, None] = "003_phase2_agent_tool_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
