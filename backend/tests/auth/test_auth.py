"""Meaningful auth tests replacing the historical placeholder assertions."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.auth.service import AuthFailure, AuthenticatedUser, AuthService


def user(role: str = "admin") -> AuthenticatedUser:
    return AuthenticatedUser(
        id=uuid4(), company_id=uuid4(), email="admin@example.test",
        full_name="Admin", role=role, company_name="Example",
        business_type="logistics", country="BD",
    )


def test_argon2_password_roundtrip_and_invalid_hash() -> None:
    service = AuthService("s" * 32)
    encoded = service.hash_password("correct horse battery staple")
    assert encoded.startswith("$argon2")
    assert service.verify_password("correct horse battery staple", encoded)
    assert not service.verify_password("wrong password", encoded)
    assert not service.verify_password("wrong password", "not-an-argon2-hash")


def test_jwt_requires_correct_issuer_and_unexpired_claims() -> None:
    now = datetime.now(timezone.utc)
    service = AuthService("s" * 32, issuer="docusense-test", access_seconds=60)
    token = service.create_access_token(user(), now=now)
    payload = service.decode_access_token(token)
    assert payload["iss"] == "docusense-test"
    assert payload["role"] == "admin"
    with pytest.raises(AuthFailure) as wrong_issuer:
        AuthService("s" * 32, issuer="other").decode_access_token(token)
    assert wrong_issuer.value.code == "UNAUTHORIZED"
    expired = service.create_access_token(user(), now=now - timedelta(minutes=2))
    with pytest.raises(AuthFailure):
        service.decode_access_token(expired)


def test_secret_and_password_policy_have_no_insecure_fallback() -> None:
    with pytest.raises(ValueError):
        AuthService("short")
    service = AuthService("s" * 32)
    with pytest.raises(ValueError):
        service.hash_password("short")


class _Mappings:
    def __init__(self, row):
        self.row = row
    def one_or_none(self):
        return self.row


class _Result:
    def __init__(self, row):
        self.row = row
    def mappings(self):
        return _Mappings(self.row)


class _Session:
    def __init__(self, row):
        self.row = row
        self.statement = ""
        self.parameters = {}
    async def execute(self, statement, parameters):
        self.statement = str(statement)
        self.parameters = parameters
        return _Result(self.row)


@pytest.mark.asyncio
async def test_authenticate_is_schema_accurate_and_tenant_joined() -> None:
    service = AuthService("s" * 32)
    account = user("operator")
    row = {
        "id": account.id, "company_id": account.company_id, "email": account.email,
        "password_hash": service.hash_password("safe password"),
        "full_name": account.full_name, "role": account.role,
        "company_name": account.company_name, "business_type": account.business_type,
        "country": account.country,
    }
    session = _Session(row)
    resolved = await service.authenticate_user(session, account.email, "safe password")
    assert resolved == account
    assert "JOIN public.companies" in session.statement
    assert "is_active" not in session.statement
    assert session.parameters == {"email": account.email}


@pytest.mark.asyncio
async def test_invalid_credentials_are_indistinguishable() -> None:
    service = AuthService("s" * 32)
    for row in (None, {
        "id": uuid4(), "company_id": uuid4(), "email": "x@example.test",
        "password_hash": service.hash_password("correct password"), "full_name": "X",
        "role": "viewer", "company_name": "X", "business_type": "other", "country": "BD",
    }):
        with pytest.raises(AuthFailure) as failure:
            await service.authenticate_user(_Session(row), "x@example.test", "wrong password")
        assert (failure.value.code, failure.value.status) == ("INVALID_CREDENTIALS", 401)
