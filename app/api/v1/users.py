"""GET /v1/users по OpenAPI Identity & Social: поиск пользователей по нику (#18117)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from tusumba_common import CurrentUser, get_current_user

from app.db import Session
from app.users import search
from app.users.search import FriendshipStatus

router = APIRouter(prefix="/users", tags=["users"])


class UserSearchItem(BaseModel):
    id: uuid.UUID
    nickname: str
    friendship_status: FriendshipStatus
    friend_request_id: uuid.UUID | None

    @classmethod
    def of(cls, found: search.FoundUser) -> "UserSearchItem":
        return cls(
            id=found.id,
            nickname=found.nickname,
            friendship_status=found.relation.status,
            friend_request_id=found.relation.request_id,
        )


class UserList(BaseModel):
    items: list[UserSearchItem]
    total: int
    page: int
    size: int


@router.get("")
async def search_users(
    db: Session,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    query: Annotated[str, Query(min_length=2, max_length=32)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> UserList:
    found, total = await search.search(db, uuid.UUID(user.id), query, page, size)
    return UserList(
        items=[UserSearchItem.of(item) for item in found], total=total, page=page, size=size
    )
