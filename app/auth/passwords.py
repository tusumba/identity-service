"""Хеширование паролей (argon2id). Сам пароль нигде не хранится."""

import asyncio

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
# Хеш для сравнения, когда пользователя нет: время ответа не выдаёт, существует ли логин.
_DUMMY_HASH = _hasher.hash("tusumba-dummy-password")


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password: str, password_hash: str | None) -> bool:
    """Проверяет пароль. Без хеша (пользователя нет) всё равно тратит то же время и даёт False."""
    target = password_hash or _DUMMY_HASH
    try:
        ok = await asyncio.to_thread(_hasher.verify, target, password)
    except (VerificationError, InvalidHashError):
        return False
    return ok and password_hash is not None
