"""Fenced orchestration over required real ports; contains no infrastructure fallback."""
from __future__ import annotations

import asyncio
from collections.abc import Sequence
import json
from typing import Protocol
from uuid import UUID

from .chunking import ChunkingService
from .confidence import score_invoice
from .embedding import EmbeddingProvider, validate_embedding_batch
from .errors import FenceLost, ProcessingError
from .extraction import ExtractionService
from .parser import DocumentParser
from .repository import ProcessingRepository
from .retrieval import RetrievalService
from .schemas import JobClaim, ProcessingIdentity, RetrievalCandidate
from .settings import ProcessingSettings

MAX_SOURCE_BYTES = 10_485_760
# Inter-attempt delays in seconds. Sized to outlast Groq's `Please try again in`
# hint for the on-demand tier (8 k TPM cap on `openai/gpt-oss-20b`) plus the
# `next_attempt_at` time we tell the reconciler to wait. With one retry
# request costing ~5–8 k tokens, three retries must span at least two minutes
# so the token bucket can refill between attempts.
RETRY_DELAYS = {1: 60, 2: 90, 3: 120}


class SourceObjectReader(Protocol):
    async def read(self, private_reference: str, maximum_bytes: int) -> bytes:
        """Read only the persisted private object and reject an oversized stream."""
        ...


def assemble_evidence(rows: Sequence[RetrievalCandidate], token_limit: int = 6000) -> str:
    """Create a bounded, visibly untrusted evidence payload without hidden prompts.

    P1: explicitly reserve a slice of the token budget for chunk_type='table'
    rows. Table cells are short, but they are the only authoritative source of
    line_item evidence; without this injection the LLM cannot synthesize
    line_items and confidence drops to near zero.
    """
    table_budget_ratio = 0.25
    # Reserve at least 30% of the budget for tables, but never the whole budget
    # unless token_limit itself is tiny.
    table_budget = int(token_limit * table_budget_ratio) if token_limit >= 1000 \
        else max(64, token_limit // 2)
    prose_budget = max(0, token_limit - table_budget)

    blocks: list[str] = []
    prose_tokens = 0
    table_tokens = 0
    seen: set[UUID] = set()

    # Pass 1: narrative + parent context within the prose budget.
    for row in rows:
        if row.chunk.chunk_type == "table":
            continue
        context = []
        if row.parent is not None and row.parent.chunk_id not in seen \
                and row.parent.chunk_type != "table":
            context.append((row.parent.chunk_id, row.parent.raw_content, row.parent.token_count))
            seen.add(row.parent.chunk_id)
        if row.chunk.chunk_id not in seen:
            context.append((row.chunk.chunk_id, row.chunk.raw_content, row.chunk.token_count))
            seen.add(row.chunk.chunk_id)
        for chunk_id, content, count in context:
            if prose_tokens + count > prose_budget:
                continue
            blocks.append(json.dumps({"chunk_id": str(chunk_id), "content": content},
                                     ensure_ascii=False, separators=(",", ":")))
            prose_tokens += count

    # Pass 2: ordered table rows by ordinal so the LLM sees the line_items source.
    table_rows = sorted(
        (row for row in rows if row.chunk.chunk_type == "table"),
        key=lambda item: (item.chunk.page_start, item.chunk.ordinal,
                          str(item.chunk.chunk_id)),
    )
    for row in table_rows:
        if row.chunk.chunk_id in seen:
            continue
        count = row.chunk.token_count
        if table_tokens + count > table_budget:
            continue
        seen.add(row.chunk.chunk_id)
        blocks.append(json.dumps(
            {"chunk_id": str(row.chunk.chunk_id), "content": row.chunk.raw_content,
             "chunk_type": "table"},
            ensure_ascii=False, separators=(",", ":"),
        ))
        table_tokens += count

    if not blocks:
        raise ProcessingError("INSUFFICIENT_EXTRACTION_EVIDENCE")
    result = "\n".join(blocks)
    if len(result) > 120_000:
        raise ProcessingError("INSUFFICIENT_EXTRACTION_EVIDENCE")
    return result


class ProcessingOrchestrator:
    def __init__(self, repository: ProcessingRepository, source: SourceObjectReader,
                 parser: DocumentParser, chunker: ChunkingService,
                 embedder: EmbeddingProvider, retriever: RetrievalService,
                 extractor: ExtractionService, settings: ProcessingSettings,
                 identity: ProcessingIdentity) -> None:
        self.repository = repository
        self.source = source
        self.parser = parser
        self.chunker = chunker
        self.embedder = embedder
        self.retriever = retriever
        self.extractor = extractor
        self.settings = settings
        self.identity = identity

    async def process(self, document_id: UUID, job_id: UUID) -> bool:
        """Process one durable pair; False means duplicate/ineligible delivery."""
        claim = await self.repository.claim(document_id, job_id, self.identity,
                                            self.settings.lease_seconds)
        if claim is None:
            return False
        fence_lost = asyncio.Event()
        work = asyncio.create_task(self._execute(claim))
        heartbeat = asyncio.create_task(self._heartbeat(claim, work, fence_lost))
        error: ProcessingError | None = None
        try:
            await asyncio.wait_for(work, timeout=self.settings.attempt_timeout_seconds)
            return True
        except asyncio.TimeoutError:
            error = ProcessingError("PROCESSING_TIMEOUT")
        except asyncio.CancelledError:
            if fence_lost.is_set():
                return False
            raise
        except ProcessingError as exc:
            error = exc
        except Exception as exc:
            import logging
            logging.getLogger("docusense.orchestrator").exception(
                "process() caught generic exception document_id=%s job_id=%s",
                claim.document_id, claim.job_id, exc_info=exc,
            )
            error = ProcessingError("PROCESSING_FAILED")
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        if fence_lost.is_set():
            return False
        assert error is not None
        delay = RETRY_DELAYS.get(claim.attempt)
        if error.retryable and delay is not None:
            await self.repository.schedule_retry(claim, error.code, delay)
        else:
            await self.repository.fail(claim, error.code)
        return False

    async def _heartbeat(self, claim: JobClaim, work: asyncio.Task[None],
                         fence_lost: asyncio.Event) -> None:
        try:
            while not work.done():
                await asyncio.sleep(self.settings.heartbeat_seconds)
                await self.repository.heartbeat(claim, self.settings.lease_seconds)
        except FenceLost:
            fence_lost.set()
            work.cancel()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Unknown heartbeat outcome cannot authorize continued writes.
            fence_lost.set()
            work.cancel()

    async def _execute(self, claim: JobClaim) -> None:
        canonical = await self.repository.load_partition(claim)
        if canonical is not None and (
            canonical.document_id != claim.document_id
            or canonical.pipeline_version != claim.identity.pipeline_version
        ):
            raise ProcessingError("PROCESSING_CONFIGURATION_CHANGED")
        if canonical is None:
            try:
                source = await asyncio.wait_for(
                    self.source.read(claim.private_reference, MAX_SOURCE_BYTES),
                    timeout=self.settings.object_read_timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise ProcessingError("SOURCE_OBJECT_UNAVAILABLE") from exc
            except ProcessingError:
                raise
            except Exception as exc:
                raise ProcessingError("SOURCE_OBJECT_UNAVAILABLE") from exc
            if not source or len(source) > MAX_SOURCE_BYTES:
                raise ProcessingError("SOURCE_OBJECT_UNAVAILABLE")
            try:
                canonical = await asyncio.wait_for(
                    self.parser.parse(claim.document_id, source),
                    timeout=self.settings.parser_timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise ProcessingError("PARSER_FAILED") from exc
            except ProcessingError:
                raise
            except Exception as exc:
                raise ProcessingError("PARSER_FAILED") from exc
            if canonical.document_id != claim.document_id or canonical.pipeline_version != claim.identity.pipeline_version:
                raise ProcessingError("PROCESSING_CONFIGURATION_CHANGED")
            await self.repository.persist_partition(claim, canonical)

        chunks = await self.repository.load_chunks(claim)
        if not chunks:
            chunks = self.chunker.build(canonical)
            await self.repository.persist_chunks(claim, chunks)

        pending = await self.repository.pending_embeddings(claim)
        for start in range(0, len(pending), self.settings.embedding_batch_size):
            batch = pending[start:start + self.settings.embedding_batch_size]
            try:
                vectors = await asyncio.wait_for(
                    self.embedder.embed(tuple(row.raw_content for row in batch)),
                    timeout=self.settings.embedding_batch_timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise ProcessingError("EMBEDDING_PROVIDER_UNAVAILABLE") from exc
            except ProcessingError:
                raise
            except Exception as exc:
                raise ProcessingError("EMBEDDING_PROVIDER_UNAVAILABLE") from exc
            embedded = validate_embedding_batch(
                tuple(row.chunk_id for row in batch), vectors,
                self.embedder.model, self.embedder.revision,
            )
            complete = start + len(batch) == len(pending)
            await self.repository.persist_embeddings(claim, embedded, complete)

        await self.repository.mark_extracting(claim)
        candidates = await self.retriever.retrieve(claim.document_id, claim.identity.pipeline_version)
        evidence = assemble_evidence(candidates, self.settings.context_tokens)
        try:
            invoice = await asyncio.wait_for(
                self.extractor.extract(evidence),
                timeout=self.settings.llm_timeout_seconds * 2,
            )
        except asyncio.TimeoutError as exc:
            raise ProcessingError("PROCESSING_TIMEOUT") from exc
        try:
            score = score_invoice(invoice)
        except ValueError as exc:
            # Field-evidence has unexpected paths or totals that don't reconcile;
            # surface a precise error code instead of the generic PROCESSING_FAILED.
            raise ProcessingError("INVALID_STRUCTURED_OUTPUT") from exc
        await self.repository.complete(claim, score)
