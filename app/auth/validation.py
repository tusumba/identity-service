"""Проверка полей регистрации и входа.

Поля проверяет сам Identity, а не pydantic: так клиент получает тексты из требований
#18109 и #18990 вместо общего текста валидации tusumba-common (см. OpenAPI).
"""

import re
from typing import Any

from app.auth import errors

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NICKNAME = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
EMAIL_MAX = 254
PASSWORD_MIN = 8
PASSWORD_MAX = 128
REQUIRED_FIELD = "Заполните обязательное поле."


def _payload(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise errors.validation_error(
            errors.INVALID_DATA_MESSAGE, [{"field": "body", "message": "Ожидается JSON-объект."}]
        )
    return body


def _blank(value: Any) -> bool:
    return not isinstance(value, str) or not value.strip()


def _require(body: dict[str, Any], fields: tuple[str, ...], message: str) -> None:
    missing = [name for name in fields if _blank(body.get(name))]
    if missing:
        raise errors.validation_error(
            message, [{"field": name, "message": REQUIRED_FIELD} for name in missing]
        )


def parse_register(body: Any) -> tuple[str, str, str]:
    """Возвращает (email, nickname, password) или бросает 422."""
    data = _payload(body)
    _require(data, ("email", "nickname", "password"), errors.REQUIRED_MESSAGE)
    email = data["email"].strip()
    nickname = data["nickname"].strip()
    password = data["password"]

    if len(email) > EMAIL_MAX or not EMAIL.match(email):
        raise errors.validation_error(
            errors.INVALID_EMAIL_MESSAGE,
            [{"field": "email", "message": errors.INVALID_EMAIL_MESSAGE}],
        )
    details: list[dict[str, str]] = []
    if not NICKNAME.match(nickname):
        details.append(
            {
                "field": "nickname",
                "message": "Ник: 3-32 символа, латиница, цифры, _, . и -.",
            }
        )
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        details.append(
            {
                "field": "password",
                "message": f"Пароль: от {PASSWORD_MIN} до {PASSWORD_MAX} символов.",
            }
        )
    if details:
        raise errors.validation_error(errors.INVALID_DATA_MESSAGE, details)
    return email, nickname, password


def parse_login(body: Any) -> tuple[str, str]:
    """Возвращает (login, password) или бросает 422 «Заполните оба поля.»."""
    data = _payload(body)
    _require(data, ("login", "password"), errors.BOTH_FIELDS_MESSAGE)
    return data["login"].strip(), data["password"]
