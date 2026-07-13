import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin
from .enums import EnvVarType


class EnvVariable(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "env_variables"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    value_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[EnvVarType] = mapped_column(
        Enum(EnvVarType, native_enum=False),
        nullable=False,
        default=EnvVarType.string,
        server_default="string",
    )

    user = relationship("User", back_populates="env_variables")
