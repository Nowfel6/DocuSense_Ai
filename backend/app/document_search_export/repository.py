"""Typed ports only; concrete SQLAlchemy awaits verified database output."""
from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import BinaryIO, Protocol
from uuid import UUID

from .schemas import (
    Caller,
    CreateExportRequest,
    DirectExportRequest,
    DocumentSearchRequest,
    ExportFormat,
    ExportResource,
    ExportStatusResource,
    SearchStatus,
)


@dataclass(frozen=True)
class EmbeddingResult:
    vector: tuple[float, ...]
    model: str
    revision: str
    normalized: bool


@dataclass(frozen=True)
class SearchRecord:
    document_id: UUID
    file_name: str
    document_type: str
    status: SearchStatus
    created_at: datetime
    invoice_id: UUID
    invoice_number: str | None
    supplier_name: str | None
    date_issued: date | None
    currency: str | None
    grand_total: Decimal | None
    is_math_valid: bool
    review_revision: int
    relevance_score: float | None = None
    matching_excerpt: str | None = None
    matching_chunk_id: UUID | None = None
    matching_page_start: int | None = None
    matching_page_end: int | None = None


@dataclass(frozen=True)
class SearchPage:
    records: tuple[SearchRecord, ...]
    total_records: int


@dataclass(frozen=True)
class ExportEstimate:
    document_count: int
    row_count: int
    uncompressed_bytes: int


@dataclass(frozen=True)
class AcceptanceOutcome:
    resource: ExportResource
    replayed: bool
    dispatch_required: bool


@dataclass(frozen=True)
class DownloadRecord:
    resource: ExportStatusResource
    object_key: str | None
    file_name: str | None
    content_type: str | None
    size_bytes: int | None
    sha256: str | None
    expires_at: datetime | None


@dataclass(frozen=True)
class ExportLine:
    line_item_id: UUID
    line_order: int
    description: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    total_price: Decimal | None


@dataclass(frozen=True)
class ExportInvoice:
    document_id: UUID
    invoice_id: UUID
    review_revision: int
    invoice_number: str | None
    supplier_name: str | None
    date_issued: date | None
    currency: str | None
    subtotal: Decimal | None
    tax_amount: Decimal | None
    grand_total: Decimal | None
    is_math_valid: bool
    lines: tuple[ExportLine, ...]


@dataclass(frozen=True)
class WorkerClaim:
    export_id: UUID
    format: ExportFormat
    attempt_count: int
    lease_token: UUID
    generated_at: datetime


@dataclass(frozen=True)
class GeneratedArtifact:
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    document_count: int
    row_count: int
    object_key: str
    completed_at: datetime
    expires_at: datetime


ProgressCallback = Callable[[str, int], Awaitable[None]]


class EmbeddingProvider(Protocol):
    async def embed_query(self, query: str) -> EmbeddingResult:
        """Return one bounded query embedding and immutable provider identity."""
        ...


class SearchRepository(Protocol):
    async def search(
        self,
        caller: Caller,
        request: DocumentSearchRequest,
        embedding: EmbeddingResult | None,
        visible_statuses: tuple[SearchStatus, ...],
    ) -> SearchPage:
        """Use tenant-first exact search and collapse before count/pagination."""
        ...


class ExportRepository(Protocol):
    async def accept(
        self,
        caller: Caller,
        request: CreateExportRequest | DirectExportRequest,
        *,
        criteria_hash: str,
        request_hash: str,
        idempotency_key_hash: str | None,
        allow_async: bool,
    ) -> AcceptanceOutcome:
        """Atomically materialize one validated selection and choose its mode."""
        ...

    async def get_status(self, caller: Caller, export_id: UUID) -> ExportStatusResource | None:
        """Return tenant-scoped safe status; None hides missing and foreign rows."""
        ...

    async def get_download(self, caller: Caller, export_id: UUID) -> DownloadRecord | None:
        """Return tenant-scoped private metadata to the query service only."""
        ...

    async def claim(self, export_id: UUID, *, lease_seconds: int) -> WorkerClaim | None:
        """Atomically claim one due async job and return its current fence."""
        ...

    async def renew(self, claim: WorkerClaim, *, lease_seconds: int) -> bool:
        """Renew only the current token-plus-attempt fence."""
        ...

    async def progress(self, claim: WorkerClaim, *, stage: str, percentage: int) -> bool:
        """Advance a current fenced attempt monotonically."""
        ...

    def source_stream(self, claim: WorkerClaim | UUID) -> AsyncIterator[ExportInvoice]:
        """Stream revalidated members from one read-only repeatable snapshot."""
        ...

    async def complete(self, claim: WorkerClaim | UUID, artifact: GeneratedArtifact) -> bool:
        """Commit terminal metadata under current async fence or sync state."""
        ...

    async def retry(self, claim: WorkerClaim, *, code: str, message: str,
                    due_at: datetime) -> bool:
        """Return current attempt to queued/accepted/0 with bounded safe reason."""
        ...

    async def fail(self, claim: WorkerClaim | UUID, *, code: str, message: str) -> bool:
        """Fail all-or-nothing and clear final/lease/retry fields."""
        ...

    async def due_dispatch(self, *, limit: int) -> tuple[UUID, ...]:
        """List bounded committed queued IDs for publish recovery."""
        ...

    async def recover_expired_leases(self, *, limit: int) -> tuple[UUID, ...]:
        """Requeue or exhaust bounded stale processing claims."""
        ...

    async def due_expiry(self, *, limit: int) -> tuple[UUID, ...]:
        """List bounded due completed IDs in indexed order."""
        ...

    async def cleanup_key(self, export_id: UUID) -> str | None:
        """Return the exact due completed object key under a scoped cleanup lock."""
        ...

    async def expire(self, export_id: UUID, expected_object_key: str) -> bool:
        """Conditionally clear one exact object key and retain provenance."""
        ...


class TaskPublisher(Protocol):
    async def publish(self, task_name: str, export_id: UUID) -> None:
        """Publish only task name and export ID."""
        ...


class StorageProvider(Protocol):
    async def put_staging(self, export_id: UUID, attempt: int, source: BinaryIO,
                          size_bytes: int, content_type: str, sha256: str) -> str:
        """Write one encrypted private attempt-scoped object and return its key."""
        ...

    async def verify(self, object_key: str, size_bytes: int, sha256: str) -> bool:
        """Verify exact private object metadata/checksum."""
        ...

    async def promote(self, staging_key: str, export_id: UUID, sha256: str) -> str:
        """Idempotently promote to the deterministic job-scoped final key."""
        ...

    async def read(self, object_key: str) -> bytes:
        """Read an already authorized completed artifact."""
        ...

    async def sign(self, object_key: str, expires_seconds: int) -> str:
        """Issue a nonpersisted private HTTPS URL."""
        ...

    async def delete_exact(self, object_key: str) -> None:
        """Delete one exact persisted key; never accept a prefix."""
        ...


__all__ = [
    "AcceptanceOutcome", "DownloadRecord", "EmbeddingProvider", "EmbeddingResult", "ExportInvoice",
    "ExportLine", "ExportRepository", "GeneratedArtifact", "SearchPage",
    "SearchRecord", "SearchRepository", "StorageProvider", "TaskPublisher",
    "WorkerClaim",
]


