"""Phase 4: rename workflow nodes_json/edges_json to nodes_data/edges_data.

NOTE: Applied by 001 create_all on fresh installs. No-op for new deploys.
"""

from typing import Sequence, Union

revision: str = "005_phase4_workflow_rename"
down_revision: Union[str, None] = "004_phase3_knowledge_base"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
