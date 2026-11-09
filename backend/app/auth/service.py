"""Concrete shared authentication against the verified auth/tenant schema."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets
import unicodedata
from typing import Literal, Protocol
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
import jwt
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


Role = Literal["admin", "operator", "viewer"]
_API_KEY = re.compile(r"^docusense_live_[0-9a-f]{32}$")

# business_type values exposed via the public signup endpoint. Subset of the
# database CHECK constraint (chk_companies_business_type), which also allows
# 'retail' — reserved for future tenant onboarding flows.
SIGNUP_BUSINESS_TYPES: frozenset[str] = frozenset({"importer", "trading", "logistics"})
_ISO_COUNTRY = re.compile(r"^[A-Z]{2}$")
_CONTROL_OR_BACKSLASH = re.compile(r"[\\\u0000-\u001f\u007f]")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_signup_inputs(
    *,
    full_name: str,
    organization_name: str,
    business_type: str,
    country: str,
    email: str,
    password: str,
    agree_to_terms: bool,
) -> None:
    """Normalize and validate signup inputs. Raises AuthFailure(VALIDATION_ERROR)."""
    if not isinstance(agree_to_terms, bool) or not agree_to_terms:
        raise AuthFailure("VALIDATION_ERROR", 400)
    full_name = unicodedata.normalize("NFKC", full_name).strip()
    organization_name = unicodedata.normalize("NFKC", organization_name).strip()
    country = country.strip().upper()
    email = email.strip()
    if not 1 <= len(full_name) <= 100 or _CONTROL_OR_BACKSLASH.search(full_name):
        raise AuthFailure("VALIDATION_ERROR", 400)
    if not 1 <= len(organization_name) <= 255 or _CONTROL_OR_BACKSLASH.search(organization_name):
        raise AuthFailure("VALIDATION_ERROR", 400)
    if business_type not in SIGNUP_BUSINESS_TYPES:
        raise AuthFailure("VALIDATION_ERROR", 400)
    if not _ISO_COUNTRY.match(country):
        raise AuthFailure("VALIDATION_ERROR", 400)
    if not _EMAIL_PATTERN.match(email) or len(email) > 255 or _CONTROL_OR_BACKSLASH.search(email):
        raise AuthFailure("VALIDATION_ERROR", 400)
    if not 8 <= len(password) <= 128:
        raise AuthFailure("VALIDATION_ERROR", 400)
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise AuthFailure("VALIDATION_ERROR", 400)


class AuthFailure(Exception):
    """Stable authentication/authorization failure without secret-bearing detail."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    company_id: UUID
    email: str
    full_name: str
    role: Role
    company_name: str
    business_type: str
    country: str


@dataclass(frozen=True)
class AuthIdentity:
    company_id: UUID
    user_id: UUID | None = None
    role: Role | None = None
    api_key_id: UUID | None = None

    def __post_init__(self) -> None:
        human = self.user_id is not None and self.role is not None and self.api_key_id is None
        machine = self.api_key_id is not None and self.user_id is None and self.role is None
        if not (human or machine):
            raise ValueError("Exactly one authentication identity is required")


@dataclass(frozen=True)
class CreatedApiKey:
    id: UUID
    key_name: str
    api_key: str
    expires_at: datetime | None
    created_at: datetime


class CredentialLike(Protocol):
    kind: Literal["bearer", "api_key"]
    secret: str


class AuthService:
    """Argon2, JWT and API-key service with schema-accurate SQL."""

    def __init__(self, jwt_secret: str, *, issuer: str = "docusense", access_seconds: int = 3600) -> None:
        if len(jwt_secret) < 32:
            raise ValueError("JWT secret must contain at least 32 characters")
        if not issuer.strip() or access_seconds < 60 or access_seconds > 86_400:
            raise ValueError("Invalid JWT issuer or access-token lifetime")
        self._secret = jwt_secret
        self.issuer = issuer.strip()
        self.access_seconds = access_seconds
        self._passwords = PasswordHasher()

    def hash_password(self, password: str) -> str:
        if not 8 <= len(password) <= 128:
            raise ValueError("Password must contain 8..128 characters")
        return self._passwords.hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            return self._passwords.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def create_access_token(self, user: AuthenticatedUser, *, now: datetime | None = None) -> str:
        issued = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        payload = {
            "iss": self.issuer,
            "sub": str(user.id),
            "company_id": str(user.company_id),
            "role": user.role,
            "iat": issued,
            "exp": issued + timedelta(seconds=self.access_seconds),
            "jti": uuid4().hex,
        }
        return jwt.encode(payload, self._secret, algorithm="HS256")

    def decode_access_token(self, token: str) -> dict[str, object]:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                issuer=self.issuer,
                options={"require": ["iss", "sub", "company_id", "role", "iat", "exp", "jti"]},
            )
            UUID(str(payload["sub"]))
            UUID(str(payload["company_id"]))
            if payload["role"] not in {"admin", "operator", "viewer"}:
                raise ValueError("Invalid role")
            return payload
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise AuthFailure("UNAUTHORIZED", 401) from exc

    async def authenticate_user(self, session: AsyncSession, email: str, password: str) -> AuthenticatedUser:
        result = await session.execute(text(
            """SELECT u.id,u.company_id,u.email,u.password_hash,u.full_name,u.role,
                      c.name AS company_name,c.business_type,c.country
               FROM public.users u JOIN public.companies c ON c.id=u.company_id
               WHERE lower(u.email)=lower(:email)"""
        ), {"email": email.strip()})
        row = result.mappings().one_or_none()
        if row is None or not self.verify_password(password, row["password_hash"]):
            raise AuthFailure("INVALID_CREDENTIALS", 401)
        return AuthenticatedUser(
            id=row["id"], company_id=row["company_id"], email=row["email"],
            full_name=row["full_name"], role=row["role"], company_name=row["company_name"],
            business_type=row["business_type"], country=row["country"],
        )

    async def current_user(self, session: AsyncSession, user_id: UUID, company_id: UUID) -> AuthenticatedUser:
        result = await session.execute(text(
            """SELECT u.id,u.company_id,u.email,u.full_name,u.role,
                      c.name AS company_name,c.business_type,c.country
               FROM public.users u JOIN public.companies c ON c.id=u.company_id
               WHERE u.id=:user_id AND u.company_id=:company_id"""
        ), {"user_id": user_id, "company_id": company_id})
        row = result.mappings().one_or_none()
        if row is None:
            raise AuthFailure("UNAUTHORIZED", 401)
        return AuthenticatedUser(**dict(row))

    async def create_api_key(
        self, session: AsyncSession, user: AuthenticatedUser, key_name: str,
        expires_at: datetime | None,
    ) -> CreatedApiKey:
        if user.role != "admin":
            raise AuthFailure("FORBIDDEN", 403)
        key_name = key_name.strip()
        if not 1 <= len(key_name) <= 100:
            raise AuthFailure("VALIDATION_ERROR", 400)
        if expires_at is not None:
            if expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc):
                raise AuthFailure("VALIDATION_ERROR", 400)
            expires_at = expires_at.astimezone(timezone.utc)
        raw_key = "docusense_live_" + secrets.token_hex(16)
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        result = await session.execute(text(
            """INSERT INTO public.api_keys (company_id,key_hash,key_name,expires_at)
               VALUES (:company_id,:key_hash,:key_name,:expires_at)
               RETURNING id,key_name,expires_at,created_at"""
        ), {
            "company_id": user.company_id, "key_hash": key_hash,
            "key_name": key_name, "expires_at": expires_at,
        })
        row = result.mappings().one()
        return CreatedApiKey(api_key=raw_key, **dict(row))

    async def signup_company_and_admin(
        self,
        session: AsyncSession,
        *,
        full_name: str,
        organization_name: str,
        business_type: str,
        country: str,
        email: str,
        password: str,
        agree_to_terms: bool,
    ) -> AuthenticatedUser:
        """Create a fresh tenant company and its first admin user atomically.

        Raises AuthFailure(VALIDATION_ERROR) for any malformed payload and
        AuthFailure(EMAIL_TAKEN) when the email already exists. The session
        is left clean: callers should ``commit()`` only on success.
        """
        _validate_signup_inputs(
            full_name=full_name,
            organization_name=organization_name,
            business_type=business_type,
            country=country,
            email=email,
            password=password,
            agree_to_terms=agree_to_terms,
        )
        company_id = uuid4()
        user_id = uuid4()
        password_hash = self.hash_password(password)
        try:
            await session.execute(text(
                """INSERT INTO public.companies (id,name,business_type,country)
                   VALUES (:id,:name,:business_type,:country)"""
            ), {
                "id": company_id, "name": organization_name.strip(),
                "business_type": business_type, "country": country,
            })
            await session.execute(text(
                """INSERT INTO public.users (id,company_id,email,password_hash,full_name,role)
                   VALUES (:id,:company_id,:email,:password_hash,:full_name,'admin')"""
            ), {
                "id": user_id, "company_id": company_id, "email": email.strip(),
                "password_hash": password_hash, "full_name": full_name.strip(),
            })
        except IntegrityError as exc:
            await session.rollback()
            message = str(exc.orig).lower()
            if "uq_users_email" in message or "users_email_key" in message:
                raise AuthFailure("EMAIL_TAKEN", 409) from exc
            raise AuthFailure("VALIDATION_ERROR", 400) from exc
        return AuthenticatedUser(
            id=user_id, company_id=company_id, email=email.strip(),
            full_name=full_name.strip(), role="admin",
            company_name=organization_name.strip(),
            business_type=business_type, country=country,
        )


class SharedAuthResolver:
    """Resolve bearer/API-key credentials and re-check persisted tenant identity."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], service: AuthService) -> None:
        self._sessions = sessions
        self._service = service

    async def resolve_identity(self, credential: CredentialLike) -> AuthIdentity:
        if credential.kind == "bearer":
            payload = self._service.decode_access_token(credential.secret)
            user_id = UUID(str(payload["sub"]))
            company_id = UUID(str(payload["company_id"]))
            async with self._sessions() as session:
                user = await self._service.current_user(session, user_id, company_id)
            if user.role != payload["role"]:
                raise AuthFailure("UNAUTHORIZED", 401)
            return AuthIdentity(company_id=company_id, user_id=user_id, role=user.role)
        if credential.kind != "api_key" or not _API_KEY.fullmatch(credential.secret):
            raise AuthFailure("UNAUTHORIZED", 401)
        digest = hashlib.sha256(credential.secret.encode("utf-8")).hexdigest()
        async with self._sessions() as session:
            result = await session.execute(text(
                """SELECT k.id,k.company_id FROM public.api_keys k
                   JOIN public.companies c ON c.id=k.company_id
                   WHERE k.key_hash=:digest
                     AND (k.expires_at IS NULL OR k.expires_at>now())"""
            ), {"digest": digest})
            row = result.mappings().one_or_none()
        if row is None:
            raise AuthFailure("UNAUTHORIZED", 401)
        return AuthIdentity(company_id=row["company_id"], api_key_id=row["id"])


__all__ = [
    "AuthFailure", "AuthenticatedUser", "AuthIdentity", "AuthService",
    "CreatedApiKey", "SharedAuthResolver", "SIGNUP_BUSINESS_TYPES",
]
