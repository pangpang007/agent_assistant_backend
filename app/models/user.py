import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True
    )
    username: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    account_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="personal", server_default="personal", index=True
    )
    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    owned_team = relationship(
        "Team",
        back_populates="owner",
        foreign_keys="Team.owner_id",
        uselist=False,
        cascade="all, delete-orphan",
    )
    team = relationship(
        "Team",
        back_populates="members",
        foreign_keys="User.team_id",
        lazy="selectin",
    )
    agents = relationship("Agent", back_populates="user", cascade="all, delete-orphan")
    tools = relationship("Tool", back_populates="user")
    knowledge_bases = relationship(
        "KnowledgeBase", back_populates="user", cascade="all, delete-orphan"
    )
    model_providers = relationship(
        "ModelProvider", back_populates="user", cascade="all, delete-orphan"
    )
    workflows = relationship("Workflow", back_populates="user", cascade="all, delete-orphan")
    env_variables = relationship(
        "EnvVariable", back_populates="user", cascade="all, delete-orphan"
    )
    model_usages = relationship("ModelUsage", back_populates="user")
