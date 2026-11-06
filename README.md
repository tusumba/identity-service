# identity-service

Сервис **Identity & Social** системы Tusumba: регистрация и вход, профиль, друзья и приглашение друга на мероприятие.

**Ответственный:** Артем Вдовин (задача #18888).

# Identity & Social

Сервис учётных записей, друзей и приглашений на мероприятия платформы Tusumba.

# Identity & Social

Сервис учётных записей, друзей и приглашений на мероприятия платформы Tusumba.

## Что делает

- регистрация, вход по почте или нику, выпуск и обновление JWT: access- и refresh-токен (RS256, закрытый ключ только у Identity, публичный ключ используют все остальные сервисы);
- поиск пользователей со статусом дружбы, запросы в друзья (отправка, входящие и отправленные, принятие и отклонение), список друзей;
- приглашение друга на мероприятие и входящие приглашения.

База данных `identity_db`: `users`, `friend_requests`, `friendships`, `event_invitations`.

## API

Внешний (через шлюз):

- `POST /v1/auth/register` - регистрация;
- `POST /v1/auth/login` - вход;
- `POST /v1/auth/refresh` - обновление токенов;
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

Описание появится после готовности шаблона сервиса (#18887) и стенда (#18905). Окружение целиком поднимается из репозитория `deploy`.

## Документация

- Внешний API: [openapi.yaml](docs/openapi.yaml), внутренний API: [openapi-internal.yaml](docs/openapi-internal.yaml) (#18888).
- Модель данных: [identity-data-model.md](docs/data-model.md) (#18888).
- Wiki проекта: https://ai.nsu.ru/projects/tusumba/wiki/Архитектура.
- Задачи ведутся в Redmine: https://ai.nsu.ru/projects/tusumba. Issues и Wiki GitHub выключены.

## Правила работы

Ветки, коммиты, pull request и code review описаны в [CONTRIBUTING.md](https://github.com/tusumba/.github/blob/main/CONTRIBUTING.md). Коротко:

- ветка называется `feature/<номер задачи Redmine>-<пара слов>`, например `feature/18901-login`;
- номер задачи указывается в каждом коммите и в названии PR;
- в `main` изменения попадают только через PR с одним одобрением и зелёным CI, прямой push и force push запрещены.
