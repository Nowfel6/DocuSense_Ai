"""Idempotently seed the demo auth/tenancy fixtures and (re)hash the demo user
passwords so the landing page can sign in with the documented credentials.

Run from `final_project/backend` with the venv active:

    python scripts/reset_demo_passwords.py

The script:
  - Inserts the three demo companies (idempotent on PK).
  - Inserts the four demo users with real Argon2id hashes (idempotent on PK).
  - Re-hashes any of those users that already exist (overwrites placeholder
    hashes like `...demoHashAdmin` that ship in `seed_auth_tenancy.sql`).

After it succeeds, you can sign in on the landing page with:
    admin@acme.com     / AdminPassword123!
    operator@acme.com  / OperatorPassword123!
    viewer@acme.com    / ViewerPassword123!
"""
from __future__ import annotations

import hashlib
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

# Make `app.*` importable when this script is run from `backend/`.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.service import AuthService  # noqa: E402

# Load .env from the final_project root so DATABASE_URL and JWT_SECRET_KEY are
# available without exporting them manually.
ENV_FILE = BACKEND_ROOT.parent / ".env"
if ENV_FILE.is_file():
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if sep and key.replace("_", "").isalnum():
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))

JWT_SECRET = os.environ["JWT_SECRET_KEY"]
# The .env URL is a plain `postgresql://...` DSN which SQLAlchemy would resolve
# to psycopg2 (not installed in this venv). Pin the driver to psycopg v3, which
# the project's foundation tooling already depends on.
_database_url = os.environ["DATABASE_URL"]
if _database_url.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + _database_url[len("postgresql://"):]
else:
    DATABASE_URL = _database_url

# Deterministic UUIDs and metadata matching database/auth/seeds/seed_auth_tenancy.sql
COMPANY_1_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")  # Acme Supply Chain BD Ltd
COMPANY_2_ID = uuid.UUID("11111111-1111-1111-1111-222222222222")  # Bengal Logistics
COMPANY_3_ID = uuid.UUID("11111111-1111-1111-1111-333333333333")  # Apex Global Trade Group

USER_ADMIN_ID    = uuid.UUID("22222222-2222-2222-2222-222222222222")
USER_OPERATOR_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
USER_VIEWER_ID   = uuid.UUID("55555555-5555-5555-5555-555555555555")
USER_BENGAL_ID   = uuid.UUID("33333333-3333-4333-8333-444444444444")

DEMO_COMPANIES = [
    {"id": COMPANY_1_ID, "name": "Acme Supply Chain BD Ltd",
     "business_type": "importer", "country": "BD"},
    {"id": COMPANY_2_ID, "name": "Bengal Logistics & Freight Solutions",
     "business_type": "logistics", "country": "BD"},
    {"id": COMPANY_3_ID, "name": "Apex Global Trade Group",
     "business_type": "trading", "country": "BD"},
]

DEMO_USERS = [
    {"id": USER_ADMIN_ID,    "company_id": COMPANY_1_ID, "email": "admin@acme.com",
     "full_name": "Acme Administrator", "role": "admin",
     "password": "AdminPassword123!"},
    {"id": USER_OPERATOR_ID, "company_id": COMPANY_1_ID, "email": "operator@acme.com",
     "full_name": "Acme Operator", "role": "operator",
     "password": "OperatorPassword123!"},
    {"id": USER_VIEWER_ID,   "company_id": COMPANY_1_ID, "email": "viewer@acme.com",
     "full_name": "Acme Auditor / Viewer", "role": "viewer",
     "password": "ViewerPassword123!"},
    {"id": USER_BENGAL_ID,   "company_id": COMPANY_2_ID, "email": "operator@bengal-logistics.example",
     "full_name": "Bengal Logistics Operator", "role": "operator",
     "password": "OperatorPassword123!"},
]


def _hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def main() -> int:
    service = AuthService(JWT_SECRET)
    engine = create_engine(DATABASE_URL, future=True)

    with engine.begin() as connection:
        # Companies: idempotent on PK.
        for company in DEMO_COMPANIES:
            connection.execute(
                text(
                    """
                    INSERT INTO public.companies
                        (id, name, business_type, country, created_at, updated_at)
                    VALUES
                        (:id, :name, :business_type, :country, NOW(), NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        business_type = EXCLUDED.business_type,
                        country = EXCLUDED.country,
                        updated_at = NOW()
                    """
                ),
                company,
            )

        # Users: real Argon2id hashes; idempotent on PK.
        for user in DEMO_USERS:
            password_hash = service.hash_password(user["password"])
            connection.execute(
                text(
                    """
                    INSERT INTO public.users
                        (id, company_id, email, password_hash, full_name,
                         role, created_at, updated_at)
                    VALUES
                        (:id, :company_id, :email, :password_hash, :full_name,
                         :role, NOW(), NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        email = EXCLUDED.email,
                        password_hash = EXCLUDED.password_hash,
                        full_name = EXCLUDED.full_name,
                        role = EXCLUDED.role,
                        updated_at = NOW()
                    """
                ),
                {**{k: v for k, v in user.items() if k != "password"},
                 "password_hash": password_hash},
            )
            print(f"  seeded/updated {user['email']} ({user['role']}) -> "
                  f"hash={password_hash[:32]}...")

        # Optional: real demo API keys (skip if the user doesn't need them).
        connection.execute(
            text(
                """
                INSERT INTO public.api_keys
                    (id, company_id, key_hash, key_name, expires_at,
                     created_at, updated_at)
                VALUES
                    (:id, :company_id, :key_hash, :key_name, :expires_at,
                     NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    key_name = EXCLUDED.key_name,
                    key_hash = EXCLUDED.key_hash,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = NOW()
                """
            ),
            {
                "id": uuid.UUID("44444444-4444-4444-4444-444444444444"),
                "company_id": COMPANY_1_ID,
                "key_hash": _hash_api_key("docusense_live_demo1234567890abcdef1234567890ab"),
                "key_name": "SAP Production Connector",
                "expires_at": datetime(2028, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO public.api_keys
                    (id, company_id, key_hash, key_name, expires_at,
                     created_at, updated_at)
                VALUES
                    (:id, :company_id, :key_hash, :key_name, :expires_at,
                     NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    key_name = EXCLUDED.key_name,
                    key_hash = EXCLUDED.key_hash,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = NOW()
                """
            ),
            {
                "id": uuid.UUID("44444444-4444-4444-4444-555555555555"),
                "company_id": COMPANY_1_ID,
                "key_hash": _hash_api_key("docusense_live_quickbooks_sync_secret_key_12345"),
                "key_name": "QuickBooks Online Sync",
                "expires_at": None,
            },
        )

    print("Done. You can sign in on the landing page with:")
    print("  admin@acme.com     / AdminPassword123!")
    print("  operator@acme.com  / OperatorPassword123!")
    print("  viewer@acme.com    / ViewerPassword123!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
