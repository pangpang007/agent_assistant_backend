import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class Tool(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tools"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="custom", server_default="custom"
    )
    openapi_spec: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    api_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    auth_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="none", server_default="none"
    )
    auth_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_preset: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    user = relationship("User", back_populates="tools")
    agent_tools = relationship(
        "AgentTool", back_populates="tool", cascade="all, delete-orphan"
    )
