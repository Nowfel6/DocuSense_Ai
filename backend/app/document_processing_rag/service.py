"""Read application service over a required tenant-scoped repository."""
from uuid import UUID

from .errors import ApiError
from .repository import TechnicalReadRepository
from .schemas import (
    CallerContext, ChunkItem, ChunkQuery, EvidenceQuery, ExtractionEvidenceData,
    InvoiceResult, Pagination,
)


class RagReadService:
    def __init__(self, repository: TechnicalReadRepository) -> None:
        if repository is None:
            raise ValueError("A concrete verified read repository is required")
        self.repository = repository

    @staticmethod
    def _technical_role(caller: CallerContext) -> None:
        if caller.api_key_id is not None or caller.role not in ("admin", "operator"):
            raise ApiError("FORBIDDEN")

    async def list_chunks(self, caller: CallerContext, document_id: UUID,
                          query: ChunkQuery) -> tuple[tuple[ChunkItem, ...], Pagination]:
        self._technical_role(caller)
        page = await self.repository.list_chunks(caller, document_id, query)
        if page is None:
            raise ApiError("DOCUMENT_NOT_FOUND")
        document = page.document
        if document.document_id != document_id or document.company_id != caller.company_id:
            raise ApiError("PROCESSING_DATA_INTEGRITY_ERROR")
        if document.progress_percentage < 40 or document.pipeline_version is None:
            raise ApiError("PROCESSING_NOT_COMPLETE")
        if len(page.rows) > query.page_size or page.total < len(page.rows):
            raise ApiError("PROCESSING_DATA_INTEGRITY_ERROR")
        ordinals = [(row.ordinal, str(row.chunk_id)) for row in page.rows]
        expected = sorted(ordinals, reverse=query.order == "desc")
        if ordinals != expected:
            raise ApiError("PROCESSING_DATA_INTEGRITY_ERROR")
        return page.rows, Pagination.create(query.page, query.page_size, page.total)

    async def get_evidence(self, caller: CallerContext, document_id: UUID,
                           query: EvidenceQuery) -> tuple[ExtractionEvidenceData, Pagination]:
        self._technical_role(caller)
        snapshot = await self.repository.get_evidence(caller, document_id, query)
        if snapshot is None:
            raise ApiError("DOCUMENT_NOT_FOUND")
        document = snapshot.document
        if document.document_id != document_id or document.company_id != caller.company_id:
            raise ApiError("PROCESSING_DATA_INTEGRITY_ERROR")
        if document.job_status != "completed" or document.progress_percentage != 100:
            raise ApiError("PROCESSING_NOT_COMPLETE")
        if snapshot.run is None or snapshot.run.status != "completed" or snapshot.validation_summary is None:
            raise ApiError("PROCESSING_DATA_INTEGRITY_ERROR")
        if len(snapshot.rows) > query.page_size or snapshot.total < len(snapshot.rows):
            raise ApiError("PROCESSING_DATA_INTEGRITY_ERROR")
        data = ExtractionEvidenceData(
            extraction_run=snapshot.run, items=snapshot.rows,
            validation_summary=snapshot.validation_summary,
            rule_results=snapshot.rule_results,
        )
        return data, Pagination.create(query.page, query.page_size, snapshot.total)

    async def get_invoice(self, caller: CallerContext, document_id: UUID) -> InvoiceResult | None:
        """Return a complete optional invoice for the already-authorized detail route."""
        invoice = await self.repository.get_invoice(caller, document_id)
        return invoice
