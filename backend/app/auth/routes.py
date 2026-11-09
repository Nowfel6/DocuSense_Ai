"""Auth route factory with explicit production dependencies and sanitized errors."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from .service import (
    SIGNUP_BUSINESS_TYPES,
    AuthFailure,
    AuthenticatedUser,
    AuthService,
)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(Model):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class CreateApiKeyRequest(Model):
    key_name: str = Field(min_length=1, max_length=100)
    expires_at: datetime | None = None


class SignupRequest(Model):
    full_name: str = Field(min_length=1, max_length=100)
    organization_name: str = Field(min_length=1, max_length=255)
    business_type: str
    country: str = Field(min_length=2, max_length=2)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    agree_to_terms: bool

    @field_validator("business_type")
    @classmethod
    def _validate_business_type(cls, value: str) -> str:
        if value not in SIGNUP_BUSINESS_TYPES:
            raise ValueError("Unsupported business_type")
        return value

    @field_validator("country")
    @classmethod
    def _validate_country(cls, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 2 or not normalized.isalpha() or not normalized.isascii():
            raise ValueError("country must be an ISO 3166-1 alpha-2 code")
        return normalized


def _raise_auth(exc: AuthFailure) -> None:
    raise HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "message": "Authentication request was rejected."},
    ) from exc


def create_auth_router(
    service: AuthService,
    session_dependency: Callable[[], AsyncIterator[AsyncSession]],
) -> APIRouter:
    """Create routes only after the host supplies a real session lifecycle."""
    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    async def current_user(
        authorization: Annotated[str, Header(min_length=8, max_length=8192)],
        session: AsyncSession = Depends(session_dependency),
    ) -> AuthenticatedUser:
        scheme, separator, token = authorization.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token:
            _raise_auth(AuthFailure("UNAUTHORIZED", 401))
        try:
            payload = service.decode_access_token(token)
            return await service.current_user(
                session, UUID(str(payload["sub"])), UUID(str(payload["company_id"])),
            )
        except (AuthFailure, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, AuthFailure):
                _raise_auth(exc)
            _raise_auth(AuthFailure("UNAUTHORIZED", 401))

    @router.post("/login", status_code=status.HTTP_200_OK)
    async def login(
        credentials: LoginRequest,
        session: AsyncSession = Depends(session_dependency),
    ) -> dict[str, object]:
        try:
            user = await service.authenticate_user(session, str(credentials.email), credentials.password)
            token = service.create_access_token(user)
        except AuthFailure as exc:
            _raise_auth(exc)
        return {
            "success": True,
            "data": {
                "access_token": token, "token_type": "bearer",
                "expires_in": service.access_seconds,
                "user": {
                    "id": str(user.id), "company_id": str(user.company_id),
                    "email": user.email, "full_name": user.full_name,
                    "role": user.role, "company_name": user.company_name,
                },
            },
            "message": "Login successful.",
        }

    @router.post("/signup", status_code=status.HTTP_201_CREATED)
    async def signup(
        request: SignupRequest,
        session: AsyncSession = Depends(session_dependency),
    ) -> dict[str, object]:
        try:
            user = await service.signup_company_and_admin(
                session,
                full_name=request.full_name,
                organization_name=request.organization_name,
                business_type=request.business_type,
                country=request.country,
                email=str(request.email),
                password=request.password,
                agree_to_terms=request.agree_to_terms,
            )
            await session.commit()
            token = service.create_access_token(user)
        except AuthFailure as exc:
            await session.rollback()
            _raise_auth(exc)
        return {
            "success": True,
            "data": {
                "access_token": token, "token_type": "bearer",
                "expires_in": service.access_seconds,
                "user": {
                    "id": str(user.id), "company_id": str(user.company_id),
                    "email": user.email, "full_name": user.full_name,
                    "role": user.role, "company_name": user.company_name,
                },
            },
            "message": "Workspace created.",
        }

    @router.post("/api-keys", status_code=status.HTTP_201_CREATED)
    async def create_key(
        request: CreateApiKeyRequest,
        user: AuthenticatedUser = Depends(current_user),
        session: AsyncSession = Depends(session_dependency),
    ) -> dict[str, object]:
        try:
            created = await service.create_api_key(session, user, request.key_name, request.expires_at)
            await session.commit()
        except AuthFailure as exc:
            await session.rollback()
            _raise_auth(exc)
        return {
            "success": True,
            "data": {
                "id": str(created.id), "key_name": created.key_name,
                "api_key": created.api_key,
                "expires_at": created.expires_at.isoformat() if created.expires_at else None,
                "created_at": created.created_at.isoformat(),
            },
            "message": "API key created.",
        }

    return router


__all__ = ["CreateApiKeyRequest", "LoginRequest", "SignupRequest", "create_auth_router"]
