import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SCHEMA, Base

GlobalRole = Literal["user", "moderator"]
GLOBAL_ROLES: tuple[GlobalRole, ...] = ("user", "moderator")


class User(Base):
    """Учётная запись. Email и ник уникальны без учёта регистра (индексы ниже)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    nickname: Mapped[str] = mapped_column(Text)
    global_role: Mapped[GlobalRole] = mapped_column(
        Enum(*GLOBAL_ROLES, name="global_role"),
        default="user",
        server_default="user",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


Index("uq_users_email_lower", func.lower(User.email), unique=True)
Index("uq_users_nickname_lower", func.lower(User.nickname), unique=True)


class RefreshToken(Base):
    """Выданный refresh-токен. Сам токен не хранится, только его jti (требование #18999)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)  # равен jti в токене
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
