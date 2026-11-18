"""Поиск пользователей по нику GET /v1/users (#19048, требование #18117)."""

from typing import Any

import httpx2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tusumba_common.testing import generate_keypair, make_token

from app.auth import tokens
from app.models import FriendRequest, Friendship, User
from app.models.friend_request import FriendRequestStatus
from app.settings import Settings


async def create_user(session: AsyncSession, nickname: str) -> User:
    user = User(email=f"{nickname}@example.com", nickname=nickname, password_hash="-")  # noqa: S106
    session.add(user)
    await session.flush()
    return user


async def create_request(
    session: AsyncSession, sender: User, recipient: User, status: FriendRequestStatus
) -> FriendRequest:
    request = FriendRequest(from_user_id=sender.id, to_user_id=recipient.id, status=status)
    session.add(request)
    await session.flush()
    return request


async def make_friends(session: AsyncSession, first: User, second: User) -> None:
    low, high = sorted((first.id, second.id))
    session.add(Friendship(user_low_id=low, user_high_id=high))
    await session.flush()


def auth(settings: Settings, user: User) -> dict[str, str]:
    token = tokens.issue_access_token(settings, user.id, user.global_role)
    return {"Authorization": f"Bearer {token}"}


async def search(
    client: httpx2.AsyncClient, headers: dict[str, str], **params: Any
) -> dict[str, Any]:
    response = await client.get("/v1/users", params=params, headers=headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def nicknames(body: dict[str, Any]) -> list[str]:
    return [item["nickname"] for item in body["items"]]


@pytest.fixture
async def me(session: AsyncSession) -> User:
    return await create_user(session, "me_searcher")


@pytest.fixture
def headers(settings: Settings, me: User) -> dict[str, str]:
    return auth(settings, me)


async def test_finds_users_by_part_of_nickname_ignoring_case(
    client: httpx2.AsyncClient, session: AsyncSession, headers: dict[str, str]
) -> None:
    for nickname in ("Alice", "malice.b", "Bob"):
        await create_user(session, nickname)

    body = await search(client, headers, query="LIC")

    assert nicknames(body) == ["Alice", "malice.b"]
    assert body["total"] == 2


async def test_wildcards_in_query_are_matched_literally(
    client: httpx2.AsyncClient, session: AsyncSession, headers: dict[str, str]
) -> None:
    await create_user(session, "ann_k")
    await create_user(session, "annak")

    assert nicknames(await search(client, headers, query="n_k")) == ["ann_k"]
    assert (await search(client, headers, query="%%"))["items"] == []


async def test_current_user_is_not_in_results(
    client: httpx2.AsyncClient, session: AsyncSession, headers: dict[str, str]
) -> None:
    await create_user(session, "searcher_two")

    assert nicknames(await search(client, headers, query="searcher")) == ["searcher_two"]


async def test_no_matches_gives_empty_page(
    client: httpx2.AsyncClient, session: AsyncSession, headers: dict[str, str]
) -> None:
    await create_user(session, "alice")

    body = await search(client, headers, query="zzz")

    assert body == {"items": [], "total": 0, "page": 1, "size": 20}


async def test_pagination(
    client: httpx2.AsyncClient, session: AsyncSession, headers: dict[str, str]
) -> None:
    for i in range(5):
        await create_user(session, f"page_user_{i}")

    first = await search(client, headers, query="page_user", page=1, size=2)
    second = await search(client, headers, query="page_user", page=2, size=2)
    last = await search(client, headers, query="page_user", page=3, size=2)
    beyond = await search(client, headers, query="page_user", page=4, size=2)

    assert (first["total"], first["page"], first["size"]) == (5, 1, 2)
    assert nicknames(first) == ["page_user_0", "page_user_1"]
    assert nicknames(second) == ["page_user_2", "page_user_3"]
    assert nicknames(last) == ["page_user_4"]
    assert beyond["items"] == []
    assert beyond["total"] == 5


async def test_returns_only_public_fields_and_friendship(
    client: httpx2.AsyncClient, session: AsyncSession, headers: dict[str, str]
) -> None:
    other = await create_user(session, "public_bob")

    body = await search(client, headers, query="public_bob")

    assert body["items"] == [
        {
            "id": str(other.id),
            "nickname": "public_bob",
            "friendship_status": "none",
            "friend_request_id": None,
        }
    ]


async def test_friendship_status(
    client: httpx2.AsyncClient, session: AsyncSession, me: User, headers: dict[str, str]
) -> None:
    stranger = await create_user(session, "fs_stranger")
    invited = await create_user(session, "fs_invited")
    inviting = await create_user(session, "fs_inviting")
    friend = await create_user(session, "fs_friend")
    declined = await create_user(session, "fs_declined")
    sent = await create_request(session, me, invited, "pending")
    received = await create_request(session, inviting, me, "pending")
    await create_request(session, friend, me, "accepted")
    await make_friends(session, me, friend)
    await create_request(session, me, declined, "declined")
    # чужой запрос не влияет на статус с текущим пользователем
    await create_request(session, stranger, invited, "pending")

    body = await search(client, headers, query="fs_")

    statuses = {
        item["nickname"]: (item["friendship_status"], item["friend_request_id"])
        for item in body["items"]
    }
    assert statuses == {
        "fs_declined": ("none", None),
        "fs_friend": ("friends", None),
        "fs_invited": ("request_sent", str(sent.id)),
        "fs_inviting": ("request_received", str(received.id)),
        "fs_stranger": ("none", None),
    }


async def test_requires_authentication(client: httpx2.AsyncClient) -> None:
    response = await client.get("/v1/users", params={"query": "alice"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize(
    ("kind", "code"),
    [
        ("garbage", "invalid_token"),
        ("foreign_key", "invalid_token"),
        ("refresh", "invalid_token"),
        ("expired", "token_expired"),
    ],
)
async def test_rejects_unusable_token(
    client: httpx2.AsyncClient, keypair: tuple[str, str], me: User, kind: str, code: str
) -> None:
    user_id = str(me.id)
    if kind == "garbage":
        token = "not-a-jwt"  # noqa: S105 - тестовое значение, не секрет
    elif kind == "foreign_key":
        token = make_token(generate_keypair()[0], user_id=user_id)
    elif kind == "refresh":
        token = make_token(keypair[0], user_id=user_id, typ="refresh")
    else:
        token = make_token(keypair[0], user_id=user_id, expires_in=-60)

    response = await client.get(
        "/v1/users", params={"query": "alice"}, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == code


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"query": "a"},
        {"query": "a" * 33},
        {"query": "ab", "page": 0},
        {"query": "ab", "size": 101},
    ],
)
async def test_validates_parameters(
    client: httpx2.AsyncClient, headers: dict[str, str], params: dict[str, Any]
) -> None:
    response = await client.get("/v1/users", params=params, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
