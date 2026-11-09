-- =============================================================================
-- Seed Fixtures: seed-auth-tenancy.sql
-- Feature: auth-tenancy
-- Purpose: Deterministic fixture data for local development & automated testing
-- Stage: 03-builds
-- =============================================================================

BEGIN;

-- 1. Demo Tenant Companies
INSERT INTO companies (id, name, business_type, country, created_at, updated_at)
VALUES 
(
    '11111111-1111-1111-1111-111111111111',
    'Acme Supply Chain BD Ltd',
    'importer',
    'BD',
    NOW(),
    NOW()
),
(
    '11111111-1111-1111-1111-222222222222',
    'Bengal Logistics & Freight Solutions',
    'logistics',
    'BD',
    NOW(),
    NOW()
),
(
    '11111111-1111-1111-1111-333333333333',
    'Apex Global Trade Group',
    'trading',
    'BD',
    NOW(),
    NOW()
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    business_type = EXCLUDED.business_type,
    country = EXCLUDED.country,
    updated_at = NOW();

-- 2. Demo Users (Admin, Operator, Viewer across Tenant 1)
-- Default passwords:
-- Admin:    AdminPassword123!
-- Operator: OperatorPassword123!
-- Viewer:   ViewerPassword123!
INSERT INTO users (id, company_id, email, password_hash, full_name, role, created_at, updated_at)
VALUES 
(
    '22222222-2222-2222-2222-222222222222',
    '11111111-1111-1111-1111-111111111111',
    'admin@acme.com',
    '$argon2id$v=19$m=65536,t=3,p=4$4P3ZgqYv2x1...demoHashAdmin',
    'Acme Administrator',
    'admin',
    NOW(),
    NOW()
),
(
    '33333333-3333-3333-3333-333333333333',
    '11111111-1111-1111-1111-111111111111',
    'operator@acme.com',
    '$argon2id$v=19$m=65536,t=3,p=4$9K4LjqYv7w2...demoHashOperator',
    'Acme Operator',
    'operator',
    NOW(),
    NOW()
),
(
    '55555555-5555-5555-5555-555555555555',
    '11111111-1111-1111-1111-111111111111',
    'viewer@acme.com',
    '$argon2id$v=19$m=65536,t=3,p=4$7M1NpqYv5z9...demoHashViewer',
    'Acme Auditor / Viewer',
    'viewer',
    NOW(),
    NOW()
),
(
    '33333333-3333-4333-8333-444444444444',
    '11111111-1111-1111-1111-222222222222',
    'operator@bengal-logistics.example',
    '$argon2id$v=19$m=65536,t=3,p=4$syntheticTenantBFixtureHash',
    'Bengal Logistics Operator',
    'operator',
    NOW(),
    NOW()
)
ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    password_hash = EXCLUDED.password_hash,
    full_name = EXCLUDED.full_name,
    role = EXCLUDED.role,
    updated_at = NOW();

-- 3. Demo API Key Fixtures
-- Key 1 Secret: docusense_live_demo1234567890abcdef1234567890ab
-- Key 2 Secret: docusense_live_quickbooks_sync_secret_key_12345
INSERT INTO api_keys (id, company_id, key_hash, key_name, expires_at, created_at, updated_at)
VALUES 
(
    '44444444-4444-4444-4444-444444444444',
    '11111111-1111-1111-1111-111111111111',
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'SAP Production Connector',
    '2028-12-31 23:59:59+00',
    NOW(),
    NOW()
),
(
    '44444444-4444-4444-4444-555555555555',
    '11111111-1111-1111-1111-111111111111',
    '8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918',
    'QuickBooks Online Sync',
    NULL,
    NOW(),
    NOW()
)
ON CONFLICT (id) DO UPDATE SET
    key_hash = EXCLUDED.key_hash,
    key_name = EXCLUDED.key_name,
    expires_at = EXCLUDED.expires_at,
    updated_at = NOW();

COMMIT;


