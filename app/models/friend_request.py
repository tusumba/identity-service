import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SCHEMA, Base

FriendRequestStatus = Literal["pending", "accepted", "declined"]
FRIEND_REQUEST_STATUSES: tuple[FriendRequestStatus, ...] = ("pending", "accepted", "declined")


class FriendRequest(Base):
    """Запрос в друзья. Строки не удаляются, меняется только статус."""

    __tablename__ = "friend_requests"
    __table_args__ = (CheckConstraint("from_user_id <> to_user_id", name="not_self"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    from_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE")
    )
    to_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE")
    )
    status: Mapped[FriendRequestStatus] = mapped_column(
        Enum(*FRIEND_REQUEST_STATUSES, name="friend_request_status"),
        default="pending",
        server_default="pending",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


_pending = FriendRequest.status == "pending"

# Не больше одного ожидающего запроса на пару в любую сторону.
Index(
    "uq_friend_requests_pending_pair",
    func.least(FriendRequest.from_user_id, FriendRequest.to_user_id),
    func.greatest(FriendRequest.from_user_id, FriendRequest.to_user_id),
    unique=True,
    postgresql_where=_pending,
)
Index(
    "ix_friend_requests_to_user_id_created_at",
    FriendRequest.to_user_id,
    FriendRequest.created_at,
    postgresql_where=_pending,
)
Index(
    "ix_friend_requests_from_user_id_created_at",
    FriendRequest.from_user_id,
    FriendRequest.created_at,
)
