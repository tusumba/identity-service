"""Поиск пользователей по нику со статусом дружбы с текущим пользователем (#18117)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FriendRequest, Friendship, User

FriendshipStatus = Literal["none", "request_sent", "request_received", "friends"]


@dataclass(frozen=True)
class Relation:
    status: FriendshipStatus
    request_id: uuid.UUID | None


NO_RELATION = Relation("none", None)


@dataclass(frozen=True)
class FoundUser:
    id: uuid.UUID
    nickname: str
    relation: Relation


async def search(
    db: AsyncSession, current_user_id: uuid.UUID, query: str, page: int, size: int
) -> tuple[list[FoundUser], int]:
    """Страница пользователей, чей ник содержит query без учёта регистра, и их общее число."""
    condition = and_(
        func.lower(User.nickname).contains(query.lower(), autoescape=True),
        User.id != current_user_id,
    )
    total = await db.scalar(select(func.count()).select_from(User).where(condition)) or 0
    rows = (
        await db.execute(
            select(User.id, User.nickname)
            .where(condition)
            .order_by(func.lower(User.nickname))
            .offset((page - 1) * size)
            .limit(size)
        )
    ).all()
    relations = await _relations(db, current_user_id, [row.id for row in rows])
    items = [FoundUser(row.id, row.nickname, relations.get(row.id, NO_RELATION)) for row in rows]
    return items, total


async def _relations(
    db: AsyncSession, current_user_id: uuid.UUID, user_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Relation]:
    if not user_ids:
        return {}
    result: dict[uuid.UUID, Relation] = {}

    pending = await db.execute(
        select(FriendRequest.id, FriendRequest.from_user_id, FriendRequest.to_user_id).where(
            FriendRequest.status == "pending",
            or_(
                and_(
                    FriendRequest.from_user_id == current_user_id,
                    FriendRequest.to_user_id.in_(user_ids),
                ),
                and_(
                    FriendRequest.to_user_id == current_user_id,
                    FriendRequest.from_user_id.in_(user_ids),
                ),
            ),
        )
    )
    for request in pending:
        if request.from_user_id == current_user_id:
            result[request.to_user_id] = Relation("request_sent", request.id)
        else:
            result[request.from_user_id] = Relation("request_received", request.id)

    friends = await db.execute(
        select(Friendship.user_low_id, Friendship.user_high_id).where(
            or_(
                and_(
                    Friendship.user_low_id == current_user_id,
                    Friendship.user_high_id.in_(user_ids),
                ),
                and_(
                    Friendship.user_high_id == current_user_id,
                    Friendship.user_low_id.in_(user_ids),
                ),
            )
        )
    )
    # дружба перекрывает статус запроса, если данные вдруг разошлись
    for pair in friends:
        other = pair.user_high_id if pair.user_low_id == current_user_id else pair.user_low_id
        result[other] = Relation("friends", None)
    return result
