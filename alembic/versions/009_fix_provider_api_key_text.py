"""Widen model_providers.api_key_encrypted to TEXT.

Revision ID: 009_fix_provider_api_key_text
Revises: 008_phase7_dashboard_api
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_fix_provider_api_key_text"
down_revision: Union[str, None] = "008_phase7_dashboard_api"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "model_providers",
        "api_key_encrypted",
        existing_type=sa.String(length=1024),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "model_providers",
        "api_key_encrypted",
        existing_type=sa.Text(),
        type_=sa.String(length=1024),
        existing_nullable=False,
    )
