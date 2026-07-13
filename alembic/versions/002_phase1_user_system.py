"""Phase 1: user system — extend users, add teams table."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_phase1_user_system"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("username", sa.String(length=100), nullable=False, server_default=""),
    )
    op.add_column(
        "users",
        sa.Column(
            "account_type",
            sa.String(length=20),
            nullable=False,
            server_default="personal",
        ),
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.execute(
        "UPDATE users SET username = split_part(email, '@', 1) WHERE username = ''"
    )
    op.alter_column("users", "username", server_default=None)

    op.create_index("ix_users_username", "users", ["username"], unique=False)
    op.create_index("ix_users_account_type", "users", ["account_type"], unique=False)

    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invite_code", sa.String(length=6), nullable=False),
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
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id"),
        sa.UniqueConstraint("invite_code"),
    )
    op.create_index("ix_teams_owner_id", "teams", ["owner_id"], unique=False)
    op.create_index("ix_teams_invite_code", "teams", ["invite_code"], unique=False)

    op.add_column("users", sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_users_team_id", "users", ["team_id"], unique=False)
    op.create_foreign_key(
        "fk_users_team_id_teams",
        "users",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_team_id_teams", "users", type_="foreignkey")
    op.drop_index("ix_users_team_id", table_name="users")
    op.drop_column("users", "team_id")

    op.drop_index("ix_teams_invite_code", table_name="teams")
    op.drop_index("ix_teams_owner_id", table_name="teams")
    op.drop_table("teams")

    op.drop_index("ix_users_account_type", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "is_active")
    op.drop_column("users", "account_type")
    op.drop_column("users", "username")
