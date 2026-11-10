"""Пути /internal для других сервисов: только с верным X-Service-Token, иначе 403.

Сейчас пусто: GET /internal/users/{id}/friends появится с задачей про друзей.
"""

from fastapi import APIRouter, Depends
from tusumba_common import require_service

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_service)])
