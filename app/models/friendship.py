import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SCHEMA, Base


class Friendship(Base):
    """Пара друзей, одна строка на пару: user_low_id < user_high_id."""

    __tablename__ = "friendships"
    __table_args__ = (CheckConstraint("user_low_id < user_high_id", name="ordered_pair"),)

    user_low_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True
    )
    user_high_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
