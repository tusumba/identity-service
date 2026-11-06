# Модель данных Identity & Social

Задача: [#18888 - OpenAPI v1 и модель данных: Identity & Social](https://ai.nsu.ru/issues/18888).
Источник: [архитектура Tusumba](https://ai.nsu.ru/projects/tusumba/wiki/Архитектура),
раздел «Identity & Social (identity_db)».

Отличие от вики: `nickname` уникален без учёта регистра, потому что вход выполняется по почте или нику.

## users

Учётные записи.

| Поле | Тип | Ключ |
|---|---|---|
| id | uuid | PK |
| email | text | UNIQUE |
| password_hash | text | |
| nickname | text | UNIQUE |
| global_role | enum (user, moderator) | |
| created_at | timestamptz | |

Уникальность: `lower(email)` и `lower(nickname)` - без учёта регистра.
Индекс: триграммный (GIN, `gin_trgm_ops`) по `lower(nickname)` - поиск по вхождению подстроки (`GET /v1/users`).
Требуется расширение `pg_trgm`: включается в первой миграции до создания индекса
(`CREATE EXTENSION IF NOT EXISTS pg_trgm`).

- `password_hash` - хеш пароля, сам пароль не хранится;
- `nickname` - латиница, цифры, `_`, `.`, `-`, 3-32 символа; символа `@` в нике нет, поэтому логин с `@` ищется по `email`, остальные - по `nickname`;
- `global_role` - по умолчанию `user`; попадает в access-токен как `roles: [global_role]` при каждом выпуске.

Регистрация по телефону текущей моделью не предусмотрена.

## friend_requests

Запросы в друзья. Строки не удаляются, меняется только статус.

| Поле | Тип | Ключ |
|---|---|---|
| id | uuid | PK |
| from_user_id | uuid | FK → users.id |
| to_user_id | uuid | FK → users.id |
| status | enum (pending, accepted, declined) | |
| created_at | timestamptz | |

Проверка: `from_user_id` ≠ `to_user_id` - нельзя отправить запрос самому себе.
Уникальность: не больше одного запроса `pending` на пару пользователей в любую сторону
(частичный уникальный индекс по `LEAST(from_user_id, to_user_id)`, `GREATEST(from_user_id, to_user_id)`
при `status = pending`).
Индексы: (`to_user_id`, `created_at`) при `status = pending` - входящие запросы, ожидающие ответа;
(`from_user_id`, `created_at`) - отправленные запросы с любым статусом (`GET /v1/friend-requests`).

- `pending` - запрос ждёт ответа адресата;
- `accepted` - запрос принят, создана строка в `friendships`;
- `declined` - запрос отклонён; после этого можно отправить новый запрос.

## friendships

Подтверждённые пары друзей, одна строка на пару.

| Поле | Тип | Ключ |
|---|---|---|
| user_low_id | uuid | PK, FK → users.id |
| user_high_id | uuid | PK, FK → users.id |
| created_at | timestamptz | |

Проверка: `user_low_id` < `user_high_id` - пару (A, B) нельзя записать второй раз как (B, A).
Индекс: (`user_high_id`) - поиск друзей по второму полю; поиск по `user_low_id` покрывает первичный ключ.

## event_invitations

Приглашения друга на мероприятие.

| Поле | Тип | Ключ |
|---|---|---|
| id | uuid | PK |
| event_id | uuid | |
| from_user_id | uuid | FK → users.id |
| to_user_id | uuid | FK → users.id |
| created_at | timestamptz | |

Проверка: `from_user_id` ≠ `to_user_id`.
Уникальность: (`event_id`, `from_user_id`, `to_user_id`) - одно приглашение друга на мероприятие от одного пользователя.
Индекс: (`to_user_id`, `created_at`) - входящие приглашения (`GET /v1/me/invitations`).

## Токены

Отдельной таблицы нет. Access- и refresh-токены - JWT RS256, подписываются закрытым ключом Identity
и в базе не хранятся. В access-токене: `sub`, `roles` (список: `[users.global_role]`), `typ = access`, `exp`;
в refresh-токене: `sub`, `typ = refresh`, `exp`, ролей нет. При обновлении `roles`
берутся из `users`. Отзыв refresh-токена до истечения срока не поддерживается.
Access-токен проверяет `get_current_user` из tusumba-common по ключу из `JWT_PUBLIC_KEY`.

## Внешние связи

`event_invitations.event_id` ссылается на `events_db.events.id` по идентификатору, без внешнего ключа.

На `users.id` по идентификатору, без внешнего ключа, ссылаются:

- `events_db`: `events.created_by_user_id`, `event_versions.edited_by`, `club_versions.edited_by`,
  `club_admins.user_id`, `event_team_members.user_id`, `team_invitations.invitee_user_id`, `team_invitations.invited_by`;
- `ticketing_db`: `payments.user_id`, `registrations.user_id`, `tickets.owner_id`, `ticket_sales_settings.updated_by`;
- `moderation_db`: `applications.author_user_id`, `applications.processed_by`, `complaints.author_user_id`,
  `complaints.processed_by`, `moderation_log.moderator_id`;
- `notifications_db`: `device_tokens.user_id`, `notification_settings.user_id`, `notifications.user_id`, `reminders.user_id`.

## Жизненный цикл запроса в друзья

1. `POST /v1/friend-requests`: проверяется, что адресат существует, это не сам пользователь, они ещё не друзья
   и между ними нет запроса `pending`. Создаётся `friend_requests` (`pending`), публикуется `FriendRequested`.
2. `POST /v1/friend-requests/{id}/accept` (только адресат): в одной транзакции `status` → `accepted`
   и создаётся строка `friendships` с упорядоченной парой (`user_low_id` < `user_high_id`).
3. `POST /v1/friend-requests/{id}/decline` (только адресат): `status` → `declined`, дружба не создаётся.
4. Запрос, адресованный другому пользователю, для `accept` и `decline` считается ненайденным
   (`friend_request_not_found`).
5. Повторный `accept` или `decline` обработанного запроса не меняет решение и возвращает
   `friend_request_not_pending`.

## Приглашение на мероприятие

`POST /v1/events/{id}/invitations`: проверяется, что адресат - друг, а мероприятие существует
и опубликовано (вызов Events & Clubs). Создаётся `event_invitations`, публикуется `EventInvitationSent`.
Список «кто из друзей идёт» строит Ticketing: друзей пользователя он получает через
`GET /internal/users/{id}/friends` и пересекает со своими `registrations`.

## API

| Запрос | Назначение | Доступ |
|---|---|---|
| POST /v1/auth/register | Регистрация по email, паролю и нику, сразу вход | Все |
| POST /v1/auth/login | Вход по почте или нику и паролю | Все |
| POST /v1/auth/refresh | Обмен refresh-токена на новую пару токенов | Все, с refresh-токеном |
| GET /v1/users?query= | Поиск пользователей по нику со статусом дружбы | Пользователь |
| GET /v1/friend-requests | Входящие запросы, ожидающие ответа, или отправленные запросы с текущим статусом | Пользователь |
| POST /v1/friend-requests | Отправка запроса в друзья | Пользователь |
| POST /v1/friend-requests/{id}/accept | Принятие запроса | Адресат запроса |
| POST /v1/friend-requests/{id}/decline | Отклонение запроса | Адресат запроса |
| GET /v1/me/friends | Мои друзья | Пользователь |
| POST /v1/events/{id}/invitations | Приглашение друга на мероприятие | Пользователь |
| GET /v1/me/invitations | Мои входящие приглашения | Пользователь |
| GET /internal/users/{id}/friends | Друзья пользователя для Ticketing | Сервисы, `X-Service-Token` |

## Коды ошибок

Формат ошибки tusumba-common: `{"error": {"code": "...", "message": "..."}}`.

| HTTP | code | Когда |
|---|---|---|
| 401 | not_authenticated | Нет заголовка Authorization (tusumba-common) |
| 401 | token_expired | Срок действия access-токена истёк (tusumba-common) |
| 401 | invalid_token | Токен недействителен или не access (tusumba-common) |
| 401 | invalid_credentials | Неверный логин или пароль |
| 401 | invalid_refresh_token | Refresh-токен недействителен или истёк |
| 403 | not_friends | Приглашение пользователя, который не является другом, в том числе самого себя |
| 403 | forbidden | Внутренний вызов без верного сервисного токена (tusumba-common) |
| 404 | user_not_found | Пользователь не найден |
| 404 | friend_request_not_found | Запрос в друзья не найден |
| 404 | event_not_found | Мероприятие не найдено или не опубликовано |
| 409 | user_already_exists | Email или ник уже заняты |
| 409 | already_friends | Пользователи уже друзья |
| 409 | friend_request_already_exists | Между пользователями уже есть запрос `pending` |
| 409 | friend_request_not_pending | Запрос уже принят или отклонён |
| 409 | invitation_already_exists | Друг уже приглашён на это мероприятие |
| 422 | validation_error | Тело или параметры запроса не прошли проверку (tusumba-common) |
| 422 | cannot_friend_self | Запрос в друзья самому себе |
| 500 | internal_error | Внутренняя ошибка или недоступен зависимый сервис |
