"""Tenant-safe search orchestration over explicit repository/provider ports."""
from __future__ import annotations

import math
from pydantic import ValidationError

from .errors import SearchExportError
from .repository import (
    EmbeddingProvider, EmbeddingResult, SearchRecord, SearchRepository,
)
from .schemas import (
    Caller,
    DocumentSearchRequest,
    DocumentSearchResult,
    Pagination,
    SearchStatus,
)
from .settings import SearchExportSettings


class SearchService:
    def __init__(self, repository: SearchRepository, embedding: EmbeddingProvider,
                 settings: SearchExportSettings) -> None:
        if repository is None or embedding is None or settings is None:
            raise ValueError("Search dependencies are mandatory")
        self._repository = repository
        self._embedding = embedding
        self._settings = settings

    async def search(
        self, caller: Caller, request: DocumentSearchRequest,
    ) -> tuple[tuple[DocumentSearchResult, ...], Pagination]:
        """Return one stable authorized result per document."""
        self._authorize(caller, request)
        self._validate_currency(request.currency)
        embedding: EmbeddingResult | None = None
        if request.query is not None:
            embedding = await self._query_embedding(request.query)
        visible: tuple[SearchStatus, ...] = (
            ("approved",) if caller.role == "viewer"
            else ("pending_review", "approved", "rejected")
        )
        page = await self._repository.search(caller, request, embedding, visible)
        if page.total_records < 0 or page.total_records < len(page.records):
            raise SearchExportError("SEARCH_DATA_INTEGRITY_ERROR")
        try:
            results = tuple(self._project(caller, row, request.query is not None)
                            for row in page.records)
        except (ValidationError, ValueError, TypeError) as exc:
            raise SearchExportError("SEARCH_DATA_INTEGRITY_ERROR") from exc
        total_pages = (
            (page.total_records + request.page_size - 1) // request.page_size
            if page.total_records else 0
        )
        pagination = Pagination(
            page=request.page,
            page_size=request.page_size,
            total_records=page.total_records,
            total_pages=total_pages,
            has_next=request.page < total_pages,
            has_prev=request.page > 1 and page.total_records > 0,
        )
        return results, pagination

    def _authorize(self, caller: Caller, request: DocumentSearchRequest) -> None:
        if not caller.is_active:
            raise SearchExportError("UNAUTHORIZED")
        if caller.auth_kind != "bearer":
            raise SearchExportError("FORBIDDEN")
        requested = set(request.document_statuses or ())
        if caller.role == "viewer" and requested - {"approved"}:
            raise SearchExportError("FORBIDDEN")

    def _validate_currency(self, currency: str | None) -> None:
        if currency is not None and currency not in self._settings.supported_currencies:
            raise SearchExportError("VALIDATION_FAILED")

    async def _query_embedding(self, query: str) -> EmbeddingResult:
        if not self._settings.embedding_revision:
            raise SearchExportError("SEARCH_CONFIGURATION_UNAVAILABLE")
        try:
            result = await self._embedding.embed_query(query)
        except SearchExportError:
            raise
        except Exception as exc:
            raise SearchExportError("SEARCH_PROVIDER_UNAVAILABLE") from exc
        if (
            result.model != self._settings.embedding_model
            or result.revision != self._settings.embedding_revision
            or not result.normalized
            or len(result.vector) != self._settings.embedding_dimension
            or any(not math.isfinite(value) for value in result.vector)
        ):
            raise SearchExportError("SEARCH_PROVIDER_UNAVAILABLE")
        norm = math.sqrt(sum(value * value for value in result.vector))
        if not math.isfinite(norm) or abs(norm - 1.0) > 1e-3:
            raise SearchExportError("SEARCH_PROVIDER_UNAVAILABLE")
        return result

    @staticmethod
    def _project(caller: Caller, record: SearchRecord,
                 semantic: bool) -> DocumentSearchResult:
        match = (
            record.relevance_score,
            record.matching_excerpt,
            record.matching_chunk_id,
            record.matching_page_start,
            record.matching_page_end,
        )
        if semantic and (
            record.relevance_score is None or record.matching_chunk_id is None
        ):
            raise ValueError("Incomplete semantic match identity")
        if not semantic and any(value is not None for value in match):
            raise ValueError("Structured search returned semantic fields")
        excerpt = record.matching_excerpt
        if excerpt is not None:
            excerpt = excerpt[:500]
        may_review = (
            caller.role in {"admin", "operator"} and record.status == "pending_review"
        ) or (caller.role == "admin" and record.status == "approved")
        return DocumentSearchResult(
            document_id=record.document_id,
            file_name=record.file_name,
            document_type=record.document_type,
            status=record.status,
            created_at=record.created_at,
            invoice_id=record.invoice_id,
            invoice_number=record.invoice_number,
            supplier_name=record.supplier_name,
            date_issued=record.date_issued,
            currency=record.currency,
            grand_total=record.grand_total,
            is_math_valid=record.is_math_valid,
            review_revision=record.review_revision,
            relevance_score=record.relevance_score,
            matching_excerpt=excerpt,
            matching_chunk_id=record.matching_chunk_id,
            matching_page_start=record.matching_page_start,
            matching_page_end=record.matching_page_end,
            export_eligible=(
                caller.role in {"admin", "operator"}
                and record.status == "approved"
                and record.document_type == "commercial_invoice"
            ),
            document_url=f"/documents/{record.document_id}",
            review_url=f"/documents/{record.document_id}/review" if may_review else None,
        )


__all__ = ["SearchService"]


