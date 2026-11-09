"""Required repository interfaces ONLY. DB implementation blocked by BE-ISSUE-001/002.

There is deliberately no SQL, SQLAlchemy mapping, fake DB, or automatic adapter.
Future adapters must import verified database-owned models and satisfy these
transaction contracts against real PostgreSQL before application wiring.
"""
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from .schemas import Caller, DocType, DocumentRecord, DocumentSummary, ListQuery, MimeType


@dataclass(frozen=True)
class AcceptanceCommand:
    document_id: UUID
    job_id: UUID
    company_id: UUID
    uploaded_by: UUID | None
    file_name: str
    file_size_bytes: int
    file_hash: str
    mime_type: MimeType
    doc_type: DocType
    private_reference: str
    confirm_duplicate: bool


@dataclass(frozen=True)
class AcceptanceReceipt:
    document_id: UUID
    job_id: UUID
    was_duplicate: bool


@dataclass(frozen=True)
class Resolution:
    state: Literal["committed", "rolled_back", "unknown"]
    receipt: AcceptanceReceipt | None = None


@dataclass(frozen=True)
class DocumentPage:
    records: tuple[DocumentSummary, ...]
    total_records: int


class DocumentRepository(Protocol):
    async def has_duplicate(self, company_id: UUID, file_hash: str) -> bool:
        """Tenant/hash precheck only; never authoritative for acceptance."""
        ...

    async def accept(self, command: AcceptanceCommand) -> AcceptanceReceipt:
        """READ COMMITTED xact advisory lock, separate recheck, atomic pair commit.

        Both confirmed/unconfirmed writers use duplicate_lock_key. Raise the
        standard duplicate error only on known rollback. Raise CommitUncertain
        for ambiguous outcomes (including cancellation crossing commit).
        Never return before commit. Do not set confidence or business approval.
        """
        ...

    async def resolve_acceptance(self, command: AcceptanceCommand) -> Resolution:
        """Authoritative pair/ID/reference resolution; absence alone is not rollback."""
        ...

    async def safe_to_remove(self, command: AcceptanceCommand) -> bool:
        """Prove no reference AND originating transaction cannot still commit.

        False on uncertain outcome, unavailable DB, missing provenance or a
        delayed in-flight writer. Never infer safety merely from missing job.
        """
        ...

    async def list_documents(self, caller: Caller, query: ListQuery) -> DocumentPage:
        """Same REPEATABLE READ snapshot for authorized count/page.

        Filter tenant and viewer approved status before count/pagination. Apply
        exact query dates, whitelisted columns/direction and same-direction UUID
        tie-breaker. Calculate upper bound for date.max inside PostgreSQL.
        """
        ...

    async def get_document(self, caller: Caller, document_id: UUID) -> DocumentRecord | None:
        """One visible document LEFT JOIN job snapshot; invisible is None.

        A visible parent with no job has job=None, so service returns 500 rather
        than concealing a pairing fault as 404. Jobs have no company_id column.
        """
        ...


class Publisher(Protocol):
    async def publish(self, document_id: UUID, job_id: UUID) -> None:
        """Publish documents.process IDs only; no attempt/state mutation."""
        ...
