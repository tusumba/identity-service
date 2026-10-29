# identity-service

Сервис **Identity & Social** системы Tusumba: регистрация и вход, профиль, друзья и приглашение друга на мероприятие.

**Ответственный:** Артем Вдовин (задача #18888).

## Что делает

- регистрация, вход, выпуск и обновление JWT (RS256, публичный ключ используют все остальные сервисы);
- поиск пользователей, запросы в друзья, список друзей;
- приглашение друга на мероприятие и входящие приглашения.

База данных `identity_db`: `users`, `friend_requests`, `friendships`, `event_invitations`.

## API

Внешний (через шлюз): `POST /v1/auth/register`, `/login`, `/refresh`; `GET /v1/users?query=`; `POST /v1/friend-requests`, `.../{id}/accept`, `.../{id}/decline`; `GET /v1/me/friends`; `POST /v1/events/{id}/invitations`; `GET /v1/me/invitations`.

Внутренний (только для сервисов): `GET /internal/users/{id}/friends`, нужен Ticketing для списка «кто из друзей идёт».

События в брокер: `FriendRequested`, `EventInvitationSent`.

Закрывает требования: #18109, #18117, #18118.

## Стек

Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL 16, RabbitMQ (FastStream).

## Запуск

Описание появится после готовности шаблона сервиса (#18887) и стенда (#18905). Окружение целиком поднимается из репозитория `deploy`.

## Документация

Wiki проекта: https://ai.nsu.ru/projects/tusumba/wiki/Архитектура. Контракт API: OpenAPI v1 (#18888). Задачи ведутся в Redmine: https://ai.nsu.ru/projects/tusumba. Issues и Wiki GitHub выключены.

## Правила работы

Ветки, коммиты, pull request и code review описаны в [CONTRIBUTING.md](https://github.com/tusumba/.github/blob/main/CONTRIBUTING.md). Коротко:

- ветка называется `feature/<номер задачи Redmine>-<пара слов>`, например `feature/18901-login`;
- номер задачи указывается в каждом коммите и в названии PR;
- в `main` изменения попадают только через PR с одним одобрением и зелёным CI, прямой push и force push запрещены.
