import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class Workflow(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "workflows"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    nodes_data: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    edges_data: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    current_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    is_published_api: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    published_api_key: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, unique=True
    )

    user = relationship("User", back_populates="workflows")
    versions = relationship(
        "WorkflowVersion",
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowVersion.version_number.desc()",
    )
    executions = relationship(
        "Execution", back_populates="workflow", cascade="all, delete-orphan"
    )
    templates = relationship("Template", back_populates="workflow")



class WorkflowVersion(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "workflow_versions"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tag: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    nodes_data: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    edges_data: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    workflow = relationship("Workflow", back_populates="versions")

    __table_args__ = (
        Index("ix_workflow_versions_wf_ver", "workflow_id", "version_number", unique=True),
    )
