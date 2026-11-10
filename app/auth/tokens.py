"""Выпуск и проверка JWT RS256: access (sub, roles, typ, exp) и refresh (sub, typ, jti, exp)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from app.settings import Settings

ACCESS = "access"
REFRESH = "refresh"


class InvalidRefreshTokenError(Exception):
    """Подпись неверна, токен повреждён или это не refresh-токен."""


@dataclass(frozen=True)
class RefreshClaims:
    user_id: uuid.UUID
    jti: uuid.UUID


def _private_pem(settings: Settings) -> str:
    # допускаем PEM с \n одной строкой, как в tusumba-common для публичного ключа
    return settings.jwt_private_key.get_secret_value().replace("\\n", "\n")


@lru_cache(maxsize=4)
def _public_pem(private_pem: str) -> str:
    key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    assert isinstance(key, RSAPrivateKey)  # noqa: S101 - ключ RS256 проверяется при запуске
    return (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )


def now() -> datetime:
    return datetime.now(UTC)


def issue_access_token(settings: Settings, user_id: uuid.UUID, role: str) -> str:
    issued = now()
    claims = {
        "sub": str(user_id),
        "roles": [role],
        "typ": ACCESS,
        "iat": issued,
        "exp": issued + timedelta(seconds=settings.access_token_ttl_seconds),
    }
    return jwt.encode(claims, _private_pem(settings), algorithm="RS256")


def issue_refresh_token(
    settings: Settings, user_id: uuid.UUID, jti: uuid.UUID, expires_at: datetime
) -> str:
    claims = {
        "sub": str(user_id),
        "typ": REFRESH,
        "jti": str(jti),
        "iat": now(),
        "exp": expires_at,
    }
    return jwt.encode(claims, _private_pem(settings), algorithm="RS256")


def decode_refresh_token(
    settings: Settings, token: str, *, verify_exp: bool = True
) -> RefreshClaims:
    """Проверяет подпись, typ = refresh и наличие sub и jti; срок - если verify_exp."""
    options: Any = {"require": ["sub", "typ", "jti", "exp"], "verify_exp": verify_exp}
    try:
        payload = jwt.decode(
            token,
            _public_pem(_private_pem(settings)),
            algorithms=["RS256"],  # только RS256: защита от alg=none и HS256
            options=options,
        )
        if payload["typ"] != REFRESH:
            raise InvalidRefreshTokenError
        return RefreshClaims(user_id=uuid.UUID(payload["sub"]), jti=uuid.UUID(payload["jti"]))
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as error:
        raise InvalidRefreshTokenError from error
