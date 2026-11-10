"""POST /v1/auth/register, /login, /refresh и /logout по OpenAPI Identity & Social."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Request, Response
from pydantic import BaseModel

from app.auth import service, validation
from app.db import Session
from app.models import User
from app.settings import Settings

router = APIRouter(prefix="/auth", tags=["auth"])

# Тела разбираем сами (validation.py): в OpenAPI это RegisterRequest, LoginRequest и RefreshRequest.
RawBody = Annotated[Any, Body()]


class UserPrivate(BaseModel):
    id: uuid.UUID
    email: str
    nickname: str
    global_role: str
    created_at: datetime

    @classmethod
    def of(cls, user: User) -> "UserPrivate":
        return cls(
            id=user.id,
            email=user.email,
            nickname=user.nickname,
            global_role=user.global_role,
            created_at=user.created_at,
        )


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int


class AuthResponse(TokenPair):
    user: UserPrivate


class RefreshRequest(BaseModel):
    refresh_token: str


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _auth_response(user: User, pair: service.TokenPair) -> AuthResponse:
    return AuthResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
        user=UserPrivate.of(user),
    )


@router.post("/register", status_code=201)
async def register(request: Request, db: Session, body: RawBody) -> AuthResponse:
    email, nickname, password = validation.parse_register(body)
    user, pair = await service.register(db, _settings(request), email, nickname, password)
    return _auth_response(user, pair)


@router.post("/login")
async def login(request: Request, db: Session, body: RawBody) -> AuthResponse:
    login_, password = validation.parse_login(body)
    user, pair = await service.login(db, _settings(request), login_, password)
    return _auth_response(user, pair)


@router.post("/refresh")
async def refresh(request: Request, db: Session, body: RefreshRequest) -> TokenPair:
    pair = await service.refresh(db, _settings(request), body.refresh_token)
    return TokenPair(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )


@router.post("/logout", status_code=204)
async def logout(request: Request, db: Session, body: RefreshRequest) -> Response:
    await service.logout(db, _settings(request), body.refresh_token)
    return Response(status_code=204)
