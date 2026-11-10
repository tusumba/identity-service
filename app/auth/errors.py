from tusumba_common import ApiError

REQUIRED_MESSAGE = "Заполните обязательные поля."
BOTH_FIELDS_MESSAGE = "Заполните оба поля."
INVALID_EMAIL_MESSAGE = "Введите корректный email."
INVALID_DATA_MESSAGE = "Проверьте введённые данные."


def validation_error(message: str, details: list[dict[str, str]]) -> ApiError:
    return ApiError(422, "validation_error", message, details=details)


def user_already_exists() -> ApiError:
    return ApiError(
        409, "user_already_exists", "Пользователь с такими данными уже зарегистрирован."
    )


def invalid_credentials() -> ApiError:
    return ApiError(401, "invalid_credentials", "Неверный логин или пароль.")


def invalid_refresh_token() -> ApiError:
    return ApiError(401, "invalid_refresh_token", "Сессия истекла, войдите заново.")
