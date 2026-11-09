-- =============================================================================
-- Migration: 20260901_create_auth_tenancy.sql
-- Feature: auth-tenancy (Multi-Tenancy & Authentication Schema)
-- Engine: PostgreSQL 15+
-- Stage: 03-builds
-- Source Spec: database_production/workflows/02-specs/auth-tenancy-db-spec.md
-- =============================================================================

BEGIN;

-- 1. Enable Native UUID Generation Extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. Standard Helper Function: Automatic updated_at Timestamp Updates
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3. Create Companies Table (Tenant Organizations)
CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    business_type VARCHAR(50) NOT NULL CONSTRAINT chk_companies_business_type 
        CHECK (business_type IN ('importer', 'trading', 'logistics', 'retail')),
    country VARCHAR(2) NOT NULL DEFAULT 'BD',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Companies updated_at Trigger
DROP TRIGGER IF EXISTS trg_companies_updated_at ON companies;
CREATE TRIGGER trg_companies_updated_at
BEFORE UPDATE ON companies
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- 4. Create Users Table (System Operators, Reviewers & Tenant Admins)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'operator' CONSTRAINT chk_users_role 
        CHECK (role IN ('admin', 'operator', 'viewer')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Users updated_at Trigger
DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- 5. Create API Keys Table (B2B ERP Integration Secrets)
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    key_hash VARCHAR(64) NOT NULL,
    key_name VARCHAR(100) NOT NULL,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- API Keys updated_at Trigger
DROP TRIGGER IF EXISTS trg_api_keys_updated_at ON api_keys;
CREATE TRIGGER trg_api_keys_updated_at
BEFORE UPDATE ON api_keys
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- 6. Performance & Uniqueness Indexes
-- Foreign Key Performance Indexes (B-Tree)
CREATE INDEX IF NOT EXISTS idx_users_company_id ON users(company_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_company_id ON api_keys(company_id);

-- Case-Insensitive Unique Login Index
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users(LOWER(email));

-- Fast API Key Lookup Unique Index
CREATE UNIQUE INDEX IF NOT EXISTS uq_api_keys_key_hash ON api_keys(key_hash);

-- Tenant Role Compound Index for Dashboard/Filter queries
CREATE INDEX IF NOT EXISTS idx_users_company_role ON users(company_id, role);

COMMIT;


