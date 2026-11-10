# identity-service

Сервис **Identity & Social** системы Tusumba: регистрация и вход, профиль, друзья и приглашение друга на мероприятие.

**Ответственный:** Артем Вдовин (задача #18888).

## Что делает

- регистрация, вход по почте или нику, выпуск и обновление JWT: access- и refresh-токен (RS256, закрытый ключ только у Identity, публичный ключ используют все остальные сервисы);
- поиск пользователей со статусом дружбы, запросы в друзья (отправка, входящие и отправленные, принятие и отклонение), список друзей;
- приглашение друга на мероприятие и входящие приглашения.

База данных `identity_db`: `users`, `refresh_tokens`, `friend_requests`, `friendships`, `event_invitations` (в миграциях пока `users` и `refresh_tokens`).

## API

Внешний (через шлюз):

- `POST /v1/auth/register` - регистрация;
- `POST /v1/auth/login` - вход;
- `POST /v1/auth/refresh` - обмен refresh-токена на новую пару токенов (ротация, #18999);
- `POST /v1/auth/logout` - выход: отзыв сессии refresh-токена;
- `GET /v1/users?query=` - поиск пользователей;
- `GET /v1/friend-requests` - входящие или отправленные запросы в друзья;
- `POST /v1/friend-requests` - отправка запроса в друзья;
- `POST /v1/friend-requests/{id}/accept` - принятие запроса;
- `POST /v1/friend-requests/{id}/decline` - отклонение запроса;
- `GET /v1/me/friends` - список друзей;
- `POST /v1/events/{id}/invitations` - приглашение друга на мероприятие;
- `GET /v1/me/invitations` - входящие приглашения.

Внутренний (только для сервисов, с сервисным токеном): `GET /internal/users/{id}/friends`, нужен Ticketing для списка «кто из друзей идёт».

События в RabbitMQ: `FriendRequested`, `EventInvitationSent`.

Закрывает требования: #18109, #18117, #18118, #18990, #18998.

## Стек

Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL 16, RabbitMQ (FastStream), tusumba-common (проверка JWT, сервисный токен, формат ошибок).

## Запуск

Нужны [uv](https://docs.astral.sh/uv/) и Docker. Сервис собран из [service-template](https://github.com/tusumba/service-template).

```bash
uv sync
cp .env.example .env
uv run python -m tusumba_common.testing dev-keys   # тестовая пара ключей: private.pem и public.pem
# впишите private.pem в JWT_PRIVATE_KEY, public.pem в JWT_PUBLIC_KEY в .env (PEM одной строкой с \n)
docker compose up -d postgres
uv run --env-file .env alembic upgrade head
uv run --env-file .env uvicorn app.main:create_app --factory --reload
```

Документация API: http://127.0.0.1:8000/docs. Окружение целиком поднимается из репозитория `deploy`.

### Переменные окружения

| Переменная | По умолчанию | Что это |
|---|---|---|
| `DATABASE_URL` | обязательна | `postgresql+asyncpg://user:password@host:5432/db` |
| `JWT_PRIVATE_KEY` | обязательна | закрытый ключ RS256 в PEM, только у Identity, подписывает токены |
| `JWT_PUBLIC_KEY` | обязательна | публичный ключ в PEM, tusumba-common проверяет им access-токены; тот же ключ задаётся всем сервисам |
| `SERVICE_TOKEN` | обязательна для `/internal` | общий сервисный токен для `X-Service-Token` |
| `ACCESS_TOKEN_TTL_SECONDS` | `900` | время жизни access-токена |
| `REFRESH_TOKEN_TTL_SECONDS` | `2592000` | время жизни refresh-токена (30 дней) |

### Проверки

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy .
uv run pytest      # PostgreSQL поднимается через testcontainers (нужен Docker)
```

Без Docker тесты идут на уже запущенном PostgreSQL: `TEST_DATABASE_URL=postgresql+asyncpg://... uv run pytest`.

## Токены и сессии

- access-токен: `sub`, `roles`, `typ = access`, `exp`; в базе не хранится, действует до `exp` (в том числе после выхода);
- refresh-токен: `sub`, `typ = refresh`, `jti`, `exp`, без ролей; `jti` лежит в таблице `refresh_tokens`;
- каждый вход или регистрация создаёт новую сессию; `/v1/auth/refresh` обменивает токен один раз, после этого он недействителен;
- повторное использование обменянного токена отзывает всю сессию, все такие случаи отвечают `401 invalid_refresh_token`;
- `/v1/auth/logout` отзывает сессию и всегда отвечает 204, если токен подписан верно (в том числе повторно и с истёкшим токеном).

Подробности: [data-model.md](docs/data-model.md).

## Документация

- Внешний API: [openapi.yaml](docs/openapi.yaml), внутренний API: [openapi-internal.yaml](docs/openapi-internal.yaml) (#18888).
- Модель данных: [data-model.md](docs/data-model.md) (#18888).
- Wiki проекта: https://ai.nsu.ru/projects/tusumba/wiki/Архитектура.
- Задачи ведутся в Redmine: https://ai.nsu.ru/projects/tusumba. Issues и Wiki GitHub выключены.

## Правила работы

Ветки, коммиты, pull request и code review описаны в [CONTRIBUTING.md](https://github.com/tusumba/.github/blob/main/CONTRIBUTING.md). Коротко:

- ветка называется `feature/<номер задачи Redmine>-<пара слов>`, например `feature/18901-login`;
- номер задачи указывается в каждом коммите и в названии PR;
- в `main` изменения попадают только через PR с одним одобрением и зелёным CI, прямой push и force push запрещены.
