import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin


class AgentKnowledgeBase(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "agent_knowledge_bases"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    agent = relationship("Agent", back_populates="agent_knowledge_bases")
    knowledge_base = relationship("KnowledgeBase", back_populates="agent_knowledge_bases")

    __table_args__ = (
        UniqueConstraint("agent_id", "knowledge_base_id", name="uq_agent_kb"),
    )
