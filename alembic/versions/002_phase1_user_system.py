"""Phase 1: user system — extend users, add teams table.

NOTE: 001_initial_schema already runs Base.metadata.create_all() with the
current models (which include Phase 1+ fields). On a fresh install those
columns/tables already exist, so this revision is a no-op for new deploys.
Kept in the chain for Alembic history.
"""

from typing import Sequence, Union

revision: str = "002_phase1_user_system"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Schema already applied by 001 create_all (current models).
    pass


def downgrade() -> None:
    pass
