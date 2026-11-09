"""Document-scoped exact retrieval and bounded evidence assembly."""
from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid5

from .embedding import EmbeddingProvider, MODEL, validate_embedding_batch
from .errors import ProcessingError
from .repository import VectorSearchRepository
from .schemas import RetrievalCandidate

OBJECTIVES = (
    "supplier_buyer", "invoice_identity_dates", "currency_totals", "line_items",
)


class RetrievalService:
    def __init__(self, embedder: EmbeddingProvider, repository: VectorSearchRepository,
                 candidate_limit: int = 24, selected_limit: int = 12,
                 context_token_limit: int = 8000) -> None:
        if not (1 <= selected_limit <= candidate_limit <= 24) or context_token_limit > 8000:
            raise ValueError("Retrieval limits exceed the approved contract")
        self.embedder = embedder
        self.repository = repository
        self.candidate_limit = candidate_limit
        self.selected_limit = selected_limit
        self.context_token_limit = context_token_limit

    async def retrieve(self, document_id: UUID, pipeline_version: str) -> tuple[RetrievalCandidate, ...]:
        raw_vectors = await self.embedder.embed(OBJECTIVES)
        query_ids = tuple(uuid5(document_id, f"retrieval:{objective}") for objective in OBJECTIVES)
        vectors = validate_embedding_batch(query_ids, raw_vectors, self.embedder.model, self.embedder.revision)
        gathered: list[RetrievalCandidate] = []
        for objective, embedded in zip(OBJECTIVES, vectors, strict=True):
            rows = await self.repository.search(
                document_id, pipeline_version, MODEL, self.embedder.revision,
                embedded.vector, objective, self.candidate_limit,
            )
            if len(rows) > self.candidate_limit:
                raise ProcessingError("PROCESSING_DATA_INTEGRITY_ERROR")
            for row in rows:
                if row.rank < 1 or row.rank > self.candidate_limit or row.chunk.retrieval_role == "parent":
                    raise ProcessingError("PROCESSING_DATA_INTEGRITY_ERROR")
                gathered.append(RetrievalCandidate(
                    chunk=row.chunk, rank=row.rank, score=row.score,
                    objective=objective, parent=row.parent,
                ))
        selected = self._select(gathered)
        if not selected:
            raise ProcessingError("INSUFFICIENT_EXTRACTION_EVIDENCE")
        return selected

    def _select(self, rows: Sequence[RetrievalCandidate]) -> tuple[RetrievalCandidate, ...]:
        ordered = sorted(rows, key=lambda item: (-item.score, item.rank, item.chunk.ordinal, str(item.chunk.chunk_id)))
        seen: set[UUID] = set()
        selected: list[RetrievalCandidate] = []
        token_total = 0
        for row in ordered:
            if row.chunk.chunk_id in seen:
                continue
            addition = row.chunk.token_count
            if row.parent is not None and row.parent.chunk_id not in seen:
                addition += row.parent.token_count
            if token_total + addition > self.context_token_limit:
                continue
            selected.append(row)
            seen.add(row.chunk.chunk_id)
            if row.parent is not None:
                seen.add(row.parent.chunk_id)
            token_total += addition
            if len(selected) == self.selected_limit:
                break
        return tuple(selected)
