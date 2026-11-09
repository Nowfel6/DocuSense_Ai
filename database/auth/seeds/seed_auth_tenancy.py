"""
DocuSense AI: Deterministic Database Seeder Script (Python)
Feature Slug: auth-tenancy
Stage: 03-builds
Usage: python seed_auth_tenancy.py
"""

import asyncio
import hashlib
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.auth.models import ApiKey, Base, Company, User

# Fixed UUID Constants for Deterministic Testing
COMPANY_1_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
COMPANY_2_ID = uuid.UUID("11111111-1111-1111-1111-222222222222")
COMPANY_3_ID = uuid.UUID("11111111-1111-1111-1111-333333333333")

USER_ADMIN_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
USER_OPERATOR_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
USER_VIEWER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")

API_KEY_1_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
API_KEY_2_ID = uuid.UUID("44444444-4444-4444-4444-555555555555")

# Mock Pre-computed Argon2 Hashes for testing
ADMIN_PASS_HASH = "$argon2id$v=19$m=65536,t=3,p=4$4P3ZgqYv2x1...demoHashAdmin"
OPERATOR_PASS_HASH = "$argon2id$v=19$m=65536,t=3,p=4$9K4LjqYv7w2...demoHashOperator"
VIEWER_PASS_HASH = "$argon2id$v=19$m=65536,t=3,p=4$7M1NpqYv5z9...demoHashViewer"


def hash_api_key(plaintext_key: str) -> str:
    """Computes SHA-256 hash of API key for secure database lookup."""
    return hashlib.sha256(plaintext_key.encode("utf-8")).hexdigest()


async def seed_auth_tenancy(session: AsyncSession) -> None:
    """Idempotently seeds auth and tenancy data into PostgreSQL."""
    print("🌱 Seeding Tenant Companies...")
    companies_data = [
        {
            "id": COMPANY_1_ID,
            "name": "Acme Supply Chain BD Ltd",
            "business_type": "importer",
            "country": "BD",
        },
        {
            "id": COMPANY_2_ID,
            "name": "Bengal Logistics & Freight Solutions",
            "business_type": "logistics",
            "country": "BD",
        },
        {
            "id": COMPANY_3_ID,
            "name": "Apex Global Trade Group",
            "business_type": "trading",
            "country": "BD",
        },
    ]

    for c_data in companies_data:
        stmt = select(Company).where(Company.id == c_data["id"])
        result = await session.execute(stmt)
        existing_company = result.scalar_one_or_none()
        if not existing_company:
            company = Company(**c_data)
            session.add(company)
            print(f"  + Added Company: {c_data['name']}")
        else:
            existing_company.name = c_data["name"]
            existing_company.business_type = c_data["business_type"]
            existing_company.country = c_data["country"]
            print(f"  * Updated Company: {c_data['name']}")

    await session.flush()

    print("🌱 Seeding Demo Users...")
    users_data = [
        {
            "id": USER_ADMIN_ID,
            "company_id": COMPANY_1_ID,
            "email": "admin@acme.com",
            "password_hash": ADMIN_PASS_HASH,
            "full_name": "Acme Administrator",
            "role": "admin",
        },
        {
            "id": USER_OPERATOR_ID,
            "company_id": COMPANY_1_ID,
            "email": "operator@acme.com",
            "password_hash": OPERATOR_PASS_HASH,
            "full_name": "Acme Operator",
            "role": "operator",
        },
        {
            "id": USER_VIEWER_ID,
            "company_id": COMPANY_1_ID,
            "email": "viewer@acme.com",
            "password_hash": VIEWER_PASS_HASH,
            "full_name": "Acme Auditor / Viewer",
            "role": "viewer",
        },
    ]

    for u_data in users_data:
        stmt = select(User).where(User.id == u_data["id"])
        result = await session.execute(stmt)
        existing_user = result.scalar_one_or_none()
        if not existing_user:
            user = User(**u_data)
            session.add(user)
            print(f"  + Added User: {u_data['email']} ({u_data['role']})")
        else:
            existing_user.email = u_data["email"]
            existing_user.password_hash = u_data["password_hash"]
            existing_user.full_name = u_data["full_name"]
            existing_user.role = u_data["role"]
            print(f"  * Updated User: {u_data['email']}")

    await session.flush()

    print("🌱 Seeding Demo API Keys...")
    api_keys_data = [
        {
            "id": API_KEY_1_ID,
            "company_id": COMPANY_1_ID,
            "key_hash": hash_api_key("docusense_live_demo1234567890abcdef1234567890ab"),
            "key_name": "SAP Production Connector",
            "expires_at": datetime(2028, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        },
        {
            "id": API_KEY_2_ID,
            "company_id": COMPANY_1_ID,
            "key_hash": hash_api_key("docusense_live_quickbooks_sync_secret_key_12345"),
            "key_name": "QuickBooks Online Sync",
            "expires_at": None,
        },
    ]

    for k_data in api_keys_data:
        stmt = select(ApiKey).where(ApiKey.id == k_data["id"])
        result = await session.execute(stmt)
        existing_key = result.scalar_one_or_none()
        if not existing_key:
            api_key = ApiKey(**k_data)
            session.add(api_key)
            print(f"  + Added API Key: {k_data['key_name']}")
        else:
            existing_key.key_name = k_data["key_name"]
            existing_key.key_hash = k_data["key_hash"]
            existing_key.expires_at = k_data["expires_at"]
            print(f"  * Updated API Key: {k_data['key_name']}")

    await session.commit()
    print("✅ Seeding completed successfully.")


async def main() -> None:
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/docusense_dev"
    )
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        await seed_auth_tenancy(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())


