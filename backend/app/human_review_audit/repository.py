"""Repository ports only; concrete SQLAlchemy awaits verified database output."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable, Protocol
from uuid import UUID

from .schemas import (
    AuditChange,
    AuditEvent,
    AuditQuery,
    Caller,
    DocumentStatus,
    EvidenceSummary,
    MutationData,
    ResolvedCandidate,
    ReviewInvoice,
    SourceView,
    ValidationBundle,
    ValidationReport,
    ValidationSummary,
)


@dataclass(frozen=True)
class ReviewSnapshot:
    document_id: UUID
    company_id: UUID
    file_name: str
    file_size_bytes: int
    mime_type: str
    doc_type: str
    status: str
    overall_confidence: Decimal | None
    created_at: datetime
    updated_at: datetime
    uploaded_by: UUID | None
    job_id: UUID
    job_status: str
    progress_percentage: int
    run_status: str | None
    run_finished_at: datetime | None
    review_revision: int
    invoice: ReviewInvoice | None
    extraction_validation: ValidationSummary | None
    field_evidence: tuple[EvidenceSummary, ...]
    latest_review_validation: ValidationReport | None
    private_reference: str
    page_count: int | None


@dataclass(frozen=True)
class PreparedAction:
    event_id: UUID
    event_action: str
    from_status: DocumentStatus
    to_status: DocumentStatus
    resulting_revision: int
    reason: str | None
    note: str | None
    request_id: str
    payload_hash: str
    candidate: ResolvedCandidate | None
    changes: tuple[AuditChange, ...]
    validation: ValidationBundle | None


@dataclass(frozen=True)
class CommandOutcome:
    data: MutationData
    replayed: bool = False


PrepareAction = Callable[[ReviewSnapshot], PreparedAction]


class ReviewRepository(Protocol):
    async def get_snapshot(self, caller: Caller, document_id: UUID) -> ReviewSnapshot | None:
        """One tenant-scoped repeatable-read snapshot; None hides missing/foreign rows."""
        ...

    async def list_audit(self, caller: Caller, document_id: UUID,
                         query: AuditQuery) -> tuple[tuple[AuditEvent, ...], int] | None:
        """Tenant predicate precedes count/page; batch changes/actor display names."""
        ...

    async def execute(self, caller: Caller, document_id: UUID,
                      idempotency_key: str | None, request_hash: str,
                      prepare: PrepareAction) -> CommandOutcome:
        """Execute the approved transaction and trigger protocol.

        A concrete adapter must reserve/replay idempotency, lock document/job/run/
        invoice/lines in order, invoke prepare while locked, stage event/changes,
        set transaction-local docusense.review_event_id, mutate current rows,
        persist validation, update revision with an old-revision predicate,
        complete replay state, and commit atomically.
        """
        ...


class SourceAccessService(Protocol):
    async def issue(self, caller: Caller, document_id: UUID, private_reference: str,
                    mime_type: str, page_count: int | None) -> SourceView:
        """Validate configured private identity and return a 300-second HTTPS view."""
        ...
