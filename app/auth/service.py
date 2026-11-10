"""Регистрация, вход, обновление и выход: сессии и ротация refresh-токенов (#18999)."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import errors, tokens
from app.auth.passwords import hash_password, verify_password
from app.models import RefreshToken, User
from app.settings import Settings


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


def _new_refresh_row(
    settings: Settings, user_id: uuid.UUID, session_id: uuid.UUID
) -> tuple[RefreshToken, datetime]:
    expires_at = tokens.now() + timedelta(seconds=settings.refresh_token_ttl_seconds)
    return RefreshToken(
        id=uuid.uuid4(), user_id=user_id, session_id=session_id, expires_at=expires_at
    ), expires_at


def _pair(settings: Settings, user: User, row: RefreshToken) -> TokenPair:
    return TokenPair(
        access_token=tokens.issue_access_token(settings, user.id, user.global_role),
        refresh_token=tokens.issue_refresh_token(settings, user.id, row.id, row.expires_at),
        expires_in=settings.access_token_ttl_seconds,
    )


async def _start_session(db: AsyncSession, settings: Settings, user: User) -> TokenPair:
    """Новый вход или регистрация: новая сессия и первый refresh-токен."""
    row, _ = _new_refresh_row(settings, user.id, uuid.uuid4())
    db.add(row)
    await db.commit()
    return _pair(settings, user, row)


async def register(
    db: AsyncSession, settings: Settings, email: str, nickname: str, password: str
) -> tuple[User, TokenPair]:
    user = User(email=email, nickname=nickname, password_hash=await hash_password(password))
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        # уникальные индексы по lower(email) и lower(nickname); гонка двух регистраций тоже здесь
        await db.rollback()
        raise errors.user_already_exists() from None
    await db.refresh(user)
    return user, await _start_session(db, settings, user)


async def login(
    db: AsyncSession, settings: Settings, login: str, password: str
) -> tuple[User, TokenPair]:
    column = User.email if "@" in login else User.nickname  # в нике @ недопустим
    user = await db.scalar(select(User).where(func.lower(column) == login.lower()))
    if not await verify_password(password, user.password_hash if user else None) or user is None:
        raise errors.invalid_credentials()
    return user, await _start_session(db, settings, user)


async def refresh(db: AsyncSession, settings: Settings, token: str) -> TokenPair:
    try:
        claims = tokens.decode_refresh_token(settings, token)
    except tokens.InvalidRefreshTokenError:
        raise errors.invalid_refresh_token() from None

    # Обмен в одной транзакции с блокировкой строки: два параллельных обмена одного токена
    # выполняются по очереди, второй видит used_at.
    row = await db.scalar(
        select(RefreshToken).where(RefreshToken.id == claims.jti).with_for_update()
    )
    now = tokens.now()
    if (
        row is None
        or row.user_id != claims.user_id
        or row.revoked_at is not None
        or row.expires_at <= now
    ):
        await db.rollback()
        raise errors.invalid_refresh_token()

    if row.used_at is not None:
        # Токен обменивают повторно: считаем кражей и отзываем всю сессию.
        await _revoke_session(db, row.session_id, now)
        await db.commit()
        raise errors.invalid_refresh_token()

    user = await db.get(User, row.user_id)
    if user is None:
        await db.rollback()
        raise errors.invalid_refresh_token()

    row.used_at = now
    new_row, _ = _new_refresh_row(settings, user.id, row.session_id)
    db.add(new_row)
    await db.commit()
    return _pair(settings, user, new_row)


async def logout(db: AsyncSession, settings: Settings, token: str) -> None:
    """Отзывает сессию токена. Истёкший, неизвестный и уже отозванный токен - не ошибка."""
    try:
        claims = tokens.decode_refresh_token(settings, token, verify_exp=False)
    except tokens.InvalidRefreshTokenError:
        raise errors.invalid_refresh_token() from None
    session_id = await db.scalar(
        select(RefreshToken.session_id).where(
            RefreshToken.id == claims.jti, RefreshToken.user_id == claims.user_id
        )
    )
    if session_id is not None:
        await _revoke_session(db, session_id, tokens.now())
    await db.commit()


async def _revoke_session(db: AsyncSession, session_id: uuid.UUID, when: datetime) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.session_id == session_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=when)
    )
