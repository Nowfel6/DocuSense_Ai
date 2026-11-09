"""Repository ports only; concrete SQLAlchemy adapters await verified DB output."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from .schemas import (
    CallerContext, CanonicalDocument, ChunkDraft, ChunkItem, ChunkQuery,
    EmbeddedChunk, EvidenceItem, EvidenceQuery, ExtractionRunInfo, InvoiceResult,
    JobClaim, ProcessingIdentity, RuleResult, ValidationBundle,
    ValidationRuleSummary, ValidationSummary,
)


@dataclass(frozen=True)
class TechnicalDocument:
    document_id: UUID
    company_id: UUID
    job_status: str
    current_stage: str
    progress_percentage: int
    run_status: str | None
    pipeline_version: str | None


@dataclass(frozen=True)
class ChunkPage:
    document: TechnicalDocument
    rows: tuple[ChunkItem, ...]
    total: int


@dataclass(frozen=True)
class EvidenceSnapshot:
    document: TechnicalDocument
    run: ExtractionRunInfo | None
    rows: tuple[EvidenceItem, ...]
    total: int
    validation_summary: ValidationSummary | None
    rule_results: tuple[ValidationRuleSummary, ...]


class TechnicalReadRepository(Protocol):
    async def list_chunks(self, caller: CallerContext, document_id: UUID,
                          query: ChunkQuery) -> ChunkPage | None:
        """One tenant-scoped repeatable-read snapshot; never select embeddings."""
        ...

    async def get_evidence(self, caller: CallerContext, document_id: UUID,
                           query: EvidenceQuery) -> EvidenceSnapshot | None:
        """One tenant/run-scoped snapshot with bounded batched relationships."""
        ...

    async def get_invoice(self, caller: CallerContext, document_id: UUID) -> InvoiceResult | None:
        """Return only a complete matching terminal graph; raise on corruption."""
        ...


class ProcessingRepository(Protocol):
    async def claim(self, document_id: UUID, job_id: UUID, identity: ProcessingIdentity,
                    lease_seconds: float) -> JobClaim | None:
        """Atomically claim with database time; None means duplicate/ineligible."""
        ...

    async def heartbeat(self, claim: JobClaim, lease_seconds: float) -> JobClaim:
        """Renew the same fence or raise FenceLost."""
        ...

    async def load_partition(self, claim: JobClaim) -> CanonicalDocument | None:
        ...

    async def persist_partition(self, claim: JobClaim, document: CanonicalDocument) -> None:
        """Persist compatible checkpoint and advance to partitioning/20 atomically."""
        ...

    async def load_chunks(self, claim: JobClaim) -> tuple[ChunkDraft, ...]:
        ...

    async def persist_chunks(self, claim: JobClaim, chunks: tuple[ChunkDraft, ...]) -> None:
        """Retry-safe upsert plus chunking/40 under the live fence."""
        ...

    async def pending_embeddings(self, claim: JobClaim) -> tuple[ChunkDraft, ...]:
        ...

    async def persist_embeddings(self, claim: JobClaim,
                                 rows: tuple[EmbeddedChunk, ...], complete: bool) -> None:
        """Persist one validated batch; advance vectorizing/60 only when complete."""
        ...

    async def mark_extracting(self, claim: JobClaim) -> None:
        """Record compatible extraction entry/80; no uncontracted candidate blob."""
        ...

    async def complete(self, claim: JobClaim, bundle: ValidationBundle) -> None:
        """Commit run/result/confidence/document pending_review/job 100 atomically."""
        ...

    async def schedule_retry(self, claim: JobClaim, code: str, delay_seconds: int) -> None:
        """Use database wall time plus the supplied 5/10/20-second delay."""
        ...

    async def fail(self, claim: JobClaim, code: str) -> None:
        """Atomically close run/job/document while retaining committed checkpoints."""
        ...


class VectorSearchRepository(Protocol):
    async def search(self, document_id: UUID, pipeline_version: str, model: str,
                     revision: str, vector: tuple[float, ...], objective: str,
                     limit: int) -> tuple["RankedChunk", ...]:
        """Apply document/model/completed predicates before exact cosine ranking."""
        ...


@dataclass(frozen=True)
class RankedChunk:
    chunk: ChunkDraft
    score: float
    rank: int
    parent: ChunkDraft | None = None
