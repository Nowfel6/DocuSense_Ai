"""Deterministic database-only oracle for Feature 06 dashboard verification.

This module does not create a new feature entity.  It describes the immutable
source facts a guarded disposable-database harness must create through the
already-approved predecessor tables.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Final


FEATURE: Final = "dashboard-activity"
FIXTURE_VERSION: Final = "1.0.0"
PREDECESSOR_HEAD: Final = "20260907_0006"
SNAPSHOT_AT: Final = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
NORMAL_FROM: Final = SNAPSHOT_AT - timedelta(days=30)
MAX_FROM: Final = SNAPSHOT_AT - timedelta(days=366)

TENANT_A: Final = uuid.UUID("da000000-0000-4000-8000-000000000001")
TENANT_B: Final = uuid.UUID("da000000-0000-4000-8000-000000000002")
VIEWER_EXPORT_SOURCE: Final = uuid.UUID("da600000-0000-4000-8000-000000000021")

APPROVED_PERFORMANCE_CORPUS: Final = {
    "tenants": 2,
    "documents_and_jobs_min": 20_000,
    "completed_extraction_runs_min": 15_000,
    "validation_results_min": 150_000,
    "review_events_min": 50_000,
    "export_jobs_min": 10_000,
    "days": 366,
    "distribution": "skewed-hot-recent-with-sparse-history",
}

APPROVED_P95_MS: Final = {
    "dashboard_30_day": 300,
    "dashboard_366_day": 750,
    "activity_first_page": 200,
    "activity_deep_page": 300,
}

INDEX_GATES: Final = {
    "minimum_p95_improvement_percent": 25,
    "maximum_write_p95_regression_percent": 10,
    "maximum_lock_acquisition_seconds": 5,
}

VALIDATION_CATALOG: Final = (
    {
        "pipeline_version": "dashboard-fixture-v1",
        "rule_id": "BR-01",
        "scope_key": "document",
        "allows_not_applicable": False,
    },
    {
        "pipeline_version": "dashboard-fixture-v1",
        "rule_id": "BR-02",
        "scope_key": "document",
        "allows_not_applicable": True,
    },
)


@dataclass(frozen=True, slots=True)
class OracleEvent:
    source_uuid: uuid.UUID
    company_id: uuid.UUID
    event_type: str
    occurred_at: datetime
    subject_type: str
    document_id: uuid.UUID | None = None
    export_id: uuid.UUID | None = None


def _id(group: int, item: int) -> uuid.UUID:
    return uuid.UUID(f"da{group:02d}0000-0000-4000-8000-{item:012d}")


TENANT_A_EVENTS: Final = (
    OracleEvent(_id(10, 1), TENANT_A, "document_uploaded", SNAPSHOT_AT - timedelta(days=2), "document", _id(1, 1)),
    OracleEvent(_id(10, 2), TENANT_A, "processing_completed", SNAPSHOT_AT - timedelta(days=2) + timedelta(minutes=4), "document", _id(1, 1)),
    OracleEvent(_id(10, 3), TENANT_A, "processing_failed", SNAPSHOT_AT - timedelta(days=3), "document", _id(1, 2)),
    OracleEvent(_id(10, 4), TENANT_A, "review_saved", SNAPSHOT_AT - timedelta(days=1, hours=4), "document", _id(1, 1)),
    OracleEvent(_id(10, 5), TENANT_A, "document_approved", SNAPSHOT_AT - timedelta(days=1), "document", _id(1, 1)),
    OracleEvent(_id(10, 6), TENANT_A, "document_rejected", SNAPSHOT_AT - timedelta(days=5), "document", _id(1, 3)),
    OracleEvent(_id(10, 7), TENANT_A, "document_reopened", SNAPSHOT_AT - timedelta(hours=12), "document", _id(1, 4)),
    OracleEvent(_id(60, 20), TENANT_A, "export_requested", SNAPSHOT_AT - timedelta(hours=6), "export", export_id=_id(60, 20)),
    OracleEvent(VIEWER_EXPORT_SOURCE, TENANT_A, "export_completed", SNAPSHOT_AT - timedelta(hours=5), "export", export_id=VIEWER_EXPORT_SOURCE),
    OracleEvent(_id(60, 22), TENANT_A, "export_failed", SNAPSHOT_AT - timedelta(hours=4), "export", export_id=_id(60, 22)),
    OracleEvent(_id(60, 23), TENANT_A, "export_expired", SNAPSHOT_AT - timedelta(hours=3), "export", export_id=_id(60, 23)),
)

TENANT_B_EVENTS: Final = (
    OracleEvent(_id(20, 1), TENANT_B, "document_uploaded", SNAPSHOT_AT - timedelta(hours=2), "document", _id(2, 1)),
    OracleEvent(_id(20, 2), TENANT_B, "document_approved", SNAPSHOT_AT - timedelta(hours=1), "document", _id(2, 1)),
)

EXPECTED_NORMAL_METRICS: Final = {
    "tenant_a": {
        "uploaded": 1,
        "processing_completed": 1,
        "processing_failed": 1,
        "review_approved": 1,
        "review_rejected": 1,
        "review_reopened": 1,
        "export_completed": 1,
        "export_failed": 1,
        "successful_processing_sample_count": 1,
        "average_successful_processing_ms": 240_000,
        "median_successful_processing_ms": 240_000,
        "initial_validation_pass_rate": Decimal("50.00"),
    },
    "tenant_b_visible_in_tenant_a": 0,
}


def opaque_viewer_export_event_id(company_id: uuid.UUID, source_uuid: uuid.UUID) -> str:
    canonical = (
        "docusense-activity-viewer-v1\0"
        f"{company_id}\0export_completed\0{source_uuid}"
    ).encode("utf-8")
    return "export_completed:opaque_" + hashlib.sha256(canonical).hexdigest()


def ordered(events: tuple[OracleEvent, ...]) -> list[OracleEvent]:
    return sorted(events, key=lambda event: (-event.occurred_at.timestamp(), event.event_type, -event.source_uuid.int))


def canonical_contract() -> dict[str, object]:
    return {
        "feature": FEATURE,
        "fixture_version": FIXTURE_VERSION,
        "predecessor_head": PREDECESSOR_HEAD,
        "snapshot_at": SNAPSHOT_AT.isoformat(),
        "performance_corpus": APPROVED_PERFORMANCE_CORPUS,
        "p95_ms": APPROVED_P95_MS,
        "index_gates": INDEX_GATES,
        "tenant_ids": [str(TENANT_A), str(TENANT_B)],
        "event_types": sorted({event.event_type for event in TENANT_A_EVENTS}),
        "viewer_export_event_id": opaque_viewer_export_event_id(TENANT_A, VIEWER_EXPORT_SOURCE),
    }


def contract_sha256() -> str:
    payload = json.dumps(canonical_contract(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def manifest_path() -> Path:
    return Path(__file__).with_name("dashboard-activity-fixtures") / "manifest.json"


def validate_manifest() -> dict[str, object]:
    manifest = json.loads(manifest_path().read_text(encoding="utf-8"))
    if manifest["contract_sha256"] != contract_sha256():
        raise ValueError("dashboard activity fixture manifest checksum mismatch")
    return manifest

