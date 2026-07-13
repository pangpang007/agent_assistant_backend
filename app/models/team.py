import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class Team(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    invite_code: Mapped[str] = mapped_column(
        String(6), unique=True, nullable=False, index=True
    )

    owner = relationship("User", back_populates="owned_team", foreign_keys=[owner_id])
    members = relationship(
        "User",
        back_populates="team",
        foreign_keys="User.team_id",
        lazy="selectin",
    )
