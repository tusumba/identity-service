"""Регистрация, вход, обновление и выход (#19038): сценарии из требований #18109, #18990, #18999."""

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import jwt
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tusumba_common import CurrentUser, get_current_user, install_error_handlers
from tusumba_common.testing import generate_keypair

from app.models import RefreshToken, User

PASSWORD = "correct horse battery"  # noqa: S105 - тестовое значение, не секрет
SESSION_EXPIRED = "Сессия истекла, войдите заново."


def registration(**overrides: Any) -> dict[str, Any]:
    body = {"email": "Ann@Example.com", "nickname": "ann", "password": PASSWORD}
    return {**body, **overrides}


async def register(client: httpx2.AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await client.post("/v1/auth/register", json=registration(**overrides))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def login(client: httpx2.AsyncClient, login_: str, password: str = PASSWORD) -> Any:
    return await client.post("/v1/auth/login", json={"login": login_, "password": password})


async def refresh(client: httpx2.AsyncClient, token: str) -> Any:
    return await client.post("/v1/auth/refresh", json={"refresh_token": token})


async def logout(client: httpx2.AsyncClient, token: str) -> Any:
    return await client.post("/v1/auth/logout", json={"refresh_token": token})


def claims(token: str, public_key: str) -> dict[str, Any]:
    payload: dict[str, Any] = jwt.decode(token, public_key, algorithms=["RS256"])
    return payload


def forged_refresh(
    private_key: str,
    *,
    user_id: str,
    jti: str | None = None,
    expires_in: int = 3600,
    typ: str = "refresh",
) -> str:
    payload = {
        "sub": user_id,
        "typ": typ,
        "jti": jti or str(uuid.uuid4()),
        "exp": int(time.time()) + expires_in,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def assert_session_expired(response: Any) -> None:
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "invalid_refresh_token"
    assert error["message"] == SESSION_EXPIRED


# --- регистрация ---


async def test_register_logs_in_and_returns_user(
    client: httpx2.AsyncClient, session: AsyncSession, keypair: tuple[str, str]
) -> None:
    body = await register(client)

    assert body["user"]["email"] == "Ann@Example.com"
    assert body["user"]["nickname"] == "ann"
    assert body["user"]["global_role"] == "user"
    assert uuid.UUID(body["user"]["id"])
    assert body["expires_in"] == 900
    access = claims(body["access_token"], keypair[1])
    assert access["sub"] == body["user"]["id"]
    assert access["roles"] == ["user"]
    assert access["typ"] == "access"
    stored = await session.scalar(select(User).where(User.id == uuid.UUID(body["user"]["id"])))
    assert stored is not None
    assert stored.password_hash.startswith("$argon2")
    assert PASSWORD not in stored.password_hash


async def test_token_passes_check_in_another_service(
    client: httpx2.AsyncClient, keypair: tuple[str, str]
) -> None:
    """Другой сервис проверяет токен через tusumba-common по публичному ключу Identity."""
    other = FastAPI()
    install_error_handlers(other)

    @other.get("/whoami")
    async def whoami(user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
        return {"id": user.id, "roles": user.roles}

    body = await register(client)
    transport = httpx2.ASGITransport(app=other)
    async with httpx2.AsyncClient(transport=transport, base_url="http://other") as service:
        ok = await service.get(
            "/whoami", headers={"Authorization": f"Bearer {body['access_token']}"}
        )
        assert ok.status_code == 200
        assert ok.json() == {"id": body["user"]["id"], "roles": ["user"]}

        # refresh-токен как access не принимается
        bad = await service.get(
            "/whoami", headers={"Authorization": f"Bearer {body['refresh_token']}"}
        )
        assert bad.status_code == 401
        assert bad.json()["error"]["code"] == "invalid_token"


async def test_refresh_token_claims(client: httpx2.AsyncClient, keypair: tuple[str, str]) -> None:
    body = await register(client)
    payload = claims(body["refresh_token"], keypair[1])
    assert payload["typ"] == "refresh"
    assert payload["sub"] == body["user"]["id"]
    assert uuid.UUID(payload["jti"])
    assert "roles" not in payload


@pytest.mark.parametrize("field", ["email", "nickname", "password"])
async def test_register_requires_all_fields(client: httpx2.AsyncClient, field: str) -> None:
    for value in (None, "", "   "):
        body = registration()
        if value is None:
            del body[field]
        else:
            body[field] = value
        response = await client.post("/v1/auth/register", json=body)
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert error["message"] == "Заполните обязательные поля."
        assert [d["field"] for d in error["details"]] == [field]


async def test_register_rejects_invalid_email(client: httpx2.AsyncClient) -> None:
    for email in ("not-an-email", "a@b", "two@@example.com", f"{'x' * 250}@example.com"):
        response = await client.post("/v1/auth/register", json=registration(email=email))
        assert response.status_code == 422, email
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert error["message"] == "Введите корректный email."


async def test_register_reports_nickname_and_password_errors_by_field(
    client: httpx2.AsyncClient,
) -> None:
    response = await client.post(
        "/v1/auth/register",
        json=registration(nickname="a@b", password="short"),  # noqa: S106
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert sorted(d["field"] for d in error["details"]) == ["nickname", "password"]


async def test_register_rejects_non_object_body(client: httpx2.AsyncClient) -> None:
    response = await client.post("/v1/auth/register", json=["ann"])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "second",
    [
        {"email": "ANN@example.com", "nickname": "other"},
        {"email": "other@example.com", "nickname": "ANN"},
    ],
)
async def test_register_rejects_taken_email_or_nickname(
    client: httpx2.AsyncClient, session: AsyncSession, second: dict[str, str]
) -> None:
    await register(client)
    response = await client.post("/v1/auth/register", json=registration(**second))
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "user_already_exists"
    assert error["message"] == "Пользователь с такими данными уже зарегистрирован."
    users = list(await session.scalars(select(User)))
    assert len(users) == 1


# --- вход ---


async def test_login_by_email_and_by_nickname_ignoring_case(client: httpx2.AsyncClient) -> None:
    registered = await register(client)
    for login_ in ("ann@example.com", "ANN@EXAMPLE.COM", "ann", "ANN"):
        response = await login(client, login_)
        assert response.status_code == 200, login_
        body = response.json()
        assert body["user"]["id"] == registered["user"]["id"]
        assert body["access_token"]
        assert body["refresh_token"]


async def test_each_login_starts_its_own_session(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    await register(client)
    await login(client, "ann")
    sessions = set(await session.scalars(select(RefreshToken.session_id)))
    assert len(sessions) == 2


async def test_login_with_wrong_password_or_unknown_user_gives_same_error(
    client: httpx2.AsyncClient,
) -> None:
    await register(client)
    wrong_password = await login(client, "ann", "wrong password")
    unknown_user = await login(client, "nobody", PASSWORD)
    for response in (wrong_password, unknown_user):
        assert response.status_code == 401
        error = response.json()["error"]
        assert error["code"] == "invalid_credentials"
        assert error["message"] == "Неверный логин или пароль."
    assert wrong_password.json() == unknown_user.json()


@pytest.mark.parametrize(
    "body", [{"login": "ann"}, {"password": PASSWORD}, {"login": " ", "password": ""}]
)
async def test_login_requires_both_fields(client: httpx2.AsyncClient, body: dict[str, str]) -> None:
    response = await client.post("/v1/auth/login", json=body)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "Заполните оба поля."


# --- обновление токена ---


async def test_refresh_exchanges_token_for_new_pair(
    client: httpx2.AsyncClient, session: AsyncSession, keypair: tuple[str, str]
) -> None:
    first = await register(client)
    response = await refresh(client, first["refresh_token"])

    assert response.status_code == 200
    second = response.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert second["expires_in"] == 900
    assert claims(second["access_token"], keypair[1])["sub"] == first["user"]["id"]

    old_jti = uuid.UUID(claims(first["refresh_token"], keypair[1])["jti"])
    new_jti = uuid.UUID(claims(second["refresh_token"], keypair[1])["jti"])
    old = await session.get(RefreshToken, old_jti)
    new = await session.get(RefreshToken, new_jti)
    assert old is not None
    assert new is not None
    assert old.used_at is not None
    assert new.used_at is None
    assert new.session_id == old.session_id  # цепочка одной сессии


async def test_refresh_takes_roles_from_database(
    client: httpx2.AsyncClient, session: AsyncSession, keypair: tuple[str, str]
) -> None:
    first = await register(client)
    await session.execute(
        update(User)
        .where(User.id == uuid.UUID(first["user"]["id"]))
        .values(global_role="moderator")
    )
    response = await refresh(client, first["refresh_token"])
    assert response.status_code == 200
    assert claims(response.json()["access_token"], keypair[1])["roles"] == ["moderator"]


async def test_exchanged_refresh_token_is_rejected_and_revokes_session(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    first = await register(client)
    second = (await refresh(client, first["refresh_token"])).json()

    reused = await refresh(client, first["refresh_token"])
    assert_session_expired(reused)

    # повторное использование отозвало всю сессию: свежий токен тоже больше не работает
    assert_session_expired(await refresh(client, second["refresh_token"]))
    rows = list(await session.scalars(select(RefreshToken)))
    assert len(rows) == 2
    assert all(row.revoked_at is not None for row in rows)


async def test_reuse_does_not_touch_other_sessions(client: httpx2.AsyncClient) -> None:
    first = await register(client)
    other_device = (await login(client, "ann")).json()
    await refresh(client, first["refresh_token"])
    assert_session_expired(await refresh(client, first["refresh_token"]))

    assert (await refresh(client, other_device["refresh_token"])).status_code == 200


async def test_refresh_rejects_unusable_tokens(
    client: httpx2.AsyncClient, session: AsyncSession, keypair: tuple[str, str]
) -> None:
    registered = await register(client)
    user_id = registered["user"]["id"]
    private_key = keypair[0]
    other_private_key, _ = generate_keypair()

    first_row = await session.scalar(select(RefreshToken))
    assert first_row is not None
    expired_row = RefreshToken(
        id=uuid.uuid4(),
        user_id=first_row.user_id,
        session_id=first_row.session_id,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    session.add(expired_row)
    await session.flush()

    candidates = {
        "мусор": "not-a-token",
        "access вместо refresh": registered["access_token"],
        "чужая подпись": forged_refresh(other_private_key, user_id=user_id),
        "нет такой записи": forged_refresh(private_key, user_id=user_id),
        "срок токена истёк": forged_refresh(
            private_key, user_id=user_id, jti=str(first_row.id), expires_in=-10
        ),
        "срок записи истёк": forged_refresh(private_key, user_id=user_id, jti=str(expired_row.id)),
        "jti другого пользователя": forged_refresh(
            private_key, user_id=str(uuid.uuid4()), jti=str(first_row.id)
        ),
    }
    for name, token in candidates.items():
        response = await refresh(client, token)
        assert response.status_code == 401, name
        assert_session_expired(response)

    # ни одна из этих попыток не отозвала настоящую сессию
    assert (await refresh(client, registered["refresh_token"])).status_code == 200


async def test_refresh_requires_token_field(client: httpx2.AsyncClient) -> None:
    response = await client.post("/v1/auth/refresh", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --- выход ---


async def test_logout_revokes_session(client: httpx2.AsyncClient, session: AsyncSession) -> None:
    body = await register(client)
    assert (await logout(client, body["refresh_token"])).status_code == 204
    assert_session_expired(await refresh(client, body["refresh_token"]))
    rows = list(await session.scalars(select(RefreshToken)))
    assert all(row.revoked_at is not None for row in rows)


async def test_logout_is_idempotent(client: httpx2.AsyncClient) -> None:
    body = await register(client)
    for _ in range(3):
        response = await logout(client, body["refresh_token"])
        assert response.status_code == 204
        assert response.content == b""


async def test_logout_revokes_whole_chain_even_with_exchanged_token(
    client: httpx2.AsyncClient,
) -> None:
    first = await register(client)
    second = (await refresh(client, first["refresh_token"])).json()
    assert (await logout(client, first["refresh_token"])).status_code == 204
    assert_session_expired(await refresh(client, second["refresh_token"]))


async def test_logout_keeps_other_sessions(client: httpx2.AsyncClient) -> None:
    first = await register(client)
    other_device = (await login(client, "ann")).json()
    assert (await logout(client, first["refresh_token"])).status_code == 204
    assert (await refresh(client, other_device["refresh_token"])).status_code == 200


async def test_logout_accepts_expired_token(
    client: httpx2.AsyncClient, session: AsyncSession, keypair: tuple[str, str]
) -> None:
    body = await register(client)
    row = await session.scalar(select(RefreshToken))
    assert row is not None
    expired = forged_refresh(
        keypair[0], user_id=body["user"]["id"], jti=str(row.id), expires_in=-10
    )
    assert (await logout(client, expired)).status_code == 204
    await session.refresh(row)
    assert row.revoked_at is not None


async def test_logout_with_unknown_token_is_not_an_error(
    client: httpx2.AsyncClient, keypair: tuple[str, str]
) -> None:
    token = forged_refresh(keypair[0], user_id=str(uuid.uuid4()))
    assert (await logout(client, token)).status_code == 204


async def test_logout_rejects_forged_or_wrong_type_token(
    client: httpx2.AsyncClient, keypair: tuple[str, str]
) -> None:
    body = await register(client)
    other_private_key, _ = generate_keypair()
    for token in (
        "not-a-token",
        body["access_token"],
        forged_refresh(other_private_key, user_id=body["user"]["id"]),
    ):
        assert_session_expired(await logout(client, token))
    assert (await refresh(client, body["refresh_token"])).status_code == 200


async def test_access_token_still_works_until_expiry_after_logout(
    client: httpx2.AsyncClient, keypair: tuple[str, str]
) -> None:
    """Access-токен в базе не хранится: сервисы проверяют его без Identity (docs/data-model.md)."""
    body = await register(client)
    await logout(client, body["refresh_token"])
    assert claims(body["access_token"], keypair[1])["sub"] == body["user"]["id"]
