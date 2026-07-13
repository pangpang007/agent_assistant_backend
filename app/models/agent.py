import uuid
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class Agent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agents"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llm_models.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    memory_strategy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="none", server_default="none"
    )
    output_format: Mapped[str] = mapped_column(
        String(20), nullable=False, default="markdown", server_default="markdown"
    )
    temperature: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.7, server_default="0.7"
    )
    max_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=4096, server_default="4096"
    )
    is_preset: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    user = relationship("User", back_populates="agents")
    model = relationship("LLMModel", back_populates="agents")
    agent_tools = relationship(
        "AgentTool", back_populates="agent", cascade="all, delete-orphan"
    )
    agent_knowledge_bases = relationship(
        "AgentKnowledgeBase", back_populates="agent", cascade="all, delete-orphan"
    )
