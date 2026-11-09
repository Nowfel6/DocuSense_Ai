"""Deterministic database-only templates for document search/export jobs.

Membership hashes are deliberately resolved by the canonical PostgreSQL function
at seed time because Feature 05 does not own or alter predecessor invoice values.
The manifest records this policy and the exact required parent identities.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "11111111-1111-1111-1111-222222222222"
ADMIN_A = "22222222-2222-2222-2222-222222222222"
OPERATOR_B = "33333333-3333-4333-8333-444444444444"
DOC_A = "66666666-6666-4666-8666-000000000001"
DOC_C = "66666666-6666-4666-8666-000000000006"
SCHEMA_VERSION = "docusense-approved-invoice-export-v1"
T0 = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)


def canonical_sha(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def job_id(number: int) -> str:
    return f"e5000000-0000-4000-8000-{number:012d}"


def _job(
    number: int,
    *,
    company_id: str,
    requester: str,
    document_id: str,
    review_revision: int,
    format: str,
    mode: str,
    target_state: str,
    idempotency_label: str | None,
) -> dict:
    criteria = {
        "selection_type": "document_ids",
        "requested_document_count": 1,
        "sort_by": "created_at",
        "order": "asc",
        "semantic_query_present": False,
        "schema_version": SCHEMA_VERSION,
    }
    criteria_hash = canonical_sha(criteria)
    request_hash = canonical_sha(
        {"format": format, "mode": mode, "criteria_hash": criteria_hash, "schema": SCHEMA_VERSION}
    )
    return {
        "id": job_id(number),
        "company_id": company_id,
        "requested_by_user_id": requester,
        "format": format,
        "mode": mode,
        "selection_type": "document_ids",
        "schema_version": SCHEMA_VERSION,
        "criteria_json": criteria,
        "criteria_hash": criteria_hash,
        "request_hash": request_hash,
        "idempotency_key_hash": canonical_sha(idempotency_label) if idempotency_label else None,
        "selected_document_count": 1,
        "request_id": f"fixture-export-{number:02d}",
        "created_at": (T0 + timedelta(minutes=number)).isoformat(),
        "document_id": document_id,
        "review_revision": review_revision,
        "target_state": target_state,
    }


def fixture_payload() -> dict:
    jobs = [
        _job(1, company_id=TENANT_A, requester=ADMIN_A, document_id=DOC_A,
             review_revision=2, format="csv", mode="synchronous",
             target_state="completed", idempotency_label="fixture-sync-csv"),
        _job(2, company_id=TENANT_A, requester=ADMIN_A, document_id=DOC_A,
             review_revision=2, format="json", mode="asynchronous",
             target_state="queued", idempotency_label="fixture-queued-json"),
        _job(3, company_id=TENANT_B, requester=OPERATOR_B, document_id=DOC_C,
             review_revision=2, format="xlsx", mode="asynchronous",
             target_state="processing", idempotency_label="fixture-processing-xlsx"),
        _job(4, company_id=TENANT_A, requester=ADMIN_A, document_id=DOC_A,
             review_revision=2, format="json", mode="asynchronous",
             target_state="failed_source_changed", idempotency_label=None),
        _job(5, company_id=TENANT_B, requester=OPERATOR_B, document_id=DOC_C,
             review_revision=2, format="xlsx", mode="asynchronous",
             target_state="expired", idempotency_label="fixture-expired-zip"),
        _job(6, company_id=TENANT_A, requester=ADMIN_A, document_id=DOC_A,
             review_revision=2, format="csv", mode="asynchronous",
             target_state="retry", idempotency_label=None),
        _job(7, company_id=TENANT_A, requester=ADMIN_A, document_id=DOC_A,
             review_revision=2, format="json", mode="asynchronous",
             target_state="completed", idempotency_label="fixture-distinct-key"),
    ]
    return {
        "scope": "DATABASE_ONLY",
        "version": 1,
        "synthetic_only": True,
        "source_hash_policy": "DATABASE_CANONICAL_FUNCTION_AT_SEED",
        "required_parents": [
            {"company_id": TENANT_A, "actor_user_id": ADMIN_A,
             "document_id": DOC_A, "review_revision": 2},
            {"company_id": TENANT_B, "actor_user_id": OPERATOR_B,
             "document_id": DOC_C, "review_revision": 2},
        ],
        "jobs": jobs,
        "memberships": [
            {"export_job_id": row["id"], "document_id": row["document_id"],
             "review_revision": row["review_revision"], "ordinal": 0,
             "source_value_hash": "DATABASE_COMPUTED"}
            for row in jobs
        ],
    }
