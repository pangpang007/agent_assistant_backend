import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class ModelProvider(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "model_providers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="custom", server_default="custom"
    )
    api_key_encrypted: Mapped[str] = mapped_column(String(1024), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    user = relationship("User", back_populates="model_providers")
    models = relationship(
        "LLMModel", back_populates="provider", cascade="all, delete-orphan"
    )


class LLMModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "llm_models"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    input_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=0, server_default="0"
    )
    output_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=0, server_default="0"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    provider = relationship("ModelProvider", back_populates="models")
    agents = relationship("Agent", back_populates="model")


class ModelUsage(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "model_usages"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_providers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llm_models.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="model_usages")
