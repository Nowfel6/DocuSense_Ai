"""Backend orchestration over required ports; never substitutes missing DB/auth."""
import asyncio
import logging
from dataclasses import replace
from typing import Protocol
from uuid import UUID, uuid4

from .errors import CommitUncertain, IngestionError, duplicate
from .pipeline import project_progress
from .repository import AcceptanceCommand, AcceptanceReceipt, DocumentRepository, Publisher
from .schemas import (
    Caller, DocumentDetail, DocumentProgress, DocumentRecord, DocumentSummary,
    ListQuery, Pagination, UploadAccepted, UploadForm, Warning,
)
from .settings import TimingSettings
from .storage import ObjectStore
from .validation import Original
from ..document_processing_rag.schemas import InvoiceResult

logger = logging.getLogger("document_ingestion")


class InvoiceReader(Protocol):
    async def get_invoice(self, caller: Caller, document_id: UUID) -> InvoiceResult | None:
        """Return the complete terminal invoice graph or raise on corruption."""
        ...


class IngestionService:
    def __init__(self, repository: DocumentRepository, storage: ObjectStore,
                 publisher: Publisher, timing: TimingSettings,
                 invoice_reader: InvoiceReader | None = None) -> None:
        self.repository, self.storage = repository, storage
        self.publisher, self.timing = publisher, timing
        self.invoice_reader = invoice_reader

    async def _cleanup(self, command: AcceptanceCommand) -> None:
        """Remove only an allocated object proven unreferenced after resolution."""
        try:
            if await self.repository.safe_to_remove(command):
                await self.storage.remove_unreferenced(command.private_reference, command.company_id, command.document_id)
            else:
                logger.warning("ingestion_object_retained document_id=%s", command.document_id)
        except Exception:
            logger.warning("ingestion_cleanup_deferred document_id=%s", command.document_id)

    async def accept_upload(self, caller: Caller, original: Original, form: UploadForm) -> UploadAccepted:
        """Authorize, store, atomically accept, then best-effort dispatch IDs."""
        if caller.role == "viewer":
            raise IngestionError("FORBIDDEN")
        if not form.confirm_duplicate and await self.repository.has_duplicate(caller.company_id, original.file_hash):
            raise duplicate()
        command = AcceptanceCommand(
            document_id=uuid4(), job_id=uuid4(), company_id=caller.company_id,
            uploaded_by=caller.user_id, file_name=original.file_name,
            file_size_bytes=len(original.content), file_hash=original.file_hash,
            mime_type=original.mime_type, doc_type=form.doc_type_hint,
            private_reference="", confirm_duplicate=form.confirm_duplicate,
        )
        command = replace(command, private_reference=self.storage.reference(
            command.company_id, command.document_id, original.extension))
        receipt: AcceptanceReceipt
        uncertain = False
        try:
            await self.storage.store(command.private_reference, original)
            try:
                receipt = await self.repository.accept(command)
            except CommitUncertain:
                uncertain = True
                resolution = await self.repository.resolve_acceptance(command)
                if resolution.state == "committed" and resolution.receipt is not None:
                    receipt = resolution.receipt
                elif resolution.state == "rolled_back":
                    uncertain = False
                    raise IngestionError("DATABASE_UNAVAILABLE")
                else:
                    # Leave object intact even if a reference lookup temporarily returns empty.
                    raise IngestionError("DATABASE_UNAVAILABLE")
        except IngestionError:
            if not uncertain:
                await self._cleanup(command)
            raise
        except BaseException:
            # Cancellation can race a commit. No immediate cleanup without a resolved proof.
            # Recovery reconciles retained objects after its grace period and fresh DB checks.
            logger.warning("ingestion_acceptance_incomplete document_id=%s", command.document_id)
            raise
        if receipt.document_id != command.document_id or receipt.job_id != command.job_id:
            raise IngestionError("INTERNAL_ERROR")
        if receipt.was_duplicate and not form.confirm_duplicate:
            raise IngestionError("INTERNAL_ERROR")
        try:
            await asyncio.wait_for(self.publisher.publish(command.document_id, command.job_id),
                                   self.timing.broker_publish_timeout_seconds)
        except Exception:
            logger.warning("ingestion_dispatch_deferred document_id=%s job_id=%s", command.document_id, command.job_id)
        warnings = []
        if receipt.was_duplicate:
            warnings.append(Warning(code="DUPLICATE_FILE_DETECTED", message="Confirmed duplicate accepted as a new document."))
        warnings.extend(original.warnings)
        return UploadAccepted(document_id=command.document_id, job_id=command.job_id,
                              file_name=original.file_name, file_size_bytes=len(original.content),
                              status_url=f"/api/v1/documents/{command.document_id}/status", warnings=warnings)

    async def _visible_record(self, caller: Caller, document_id: UUID) -> DocumentRecord:
        """Verify the repository's authorized pair projection before exposing it."""
        record = await self.repository.get_document(caller, document_id)
        if record is None or record.company_id != caller.company_id or (caller.role == "viewer" and record.summary.status != "approved"):
            raise IngestionError("DOCUMENT_NOT_FOUND")
        if record.summary.document_id != document_id or record.job is None or record.job.document_id != document_id:
            raise IngestionError("INTERNAL_ERROR")
        return record

    async def get_progress(self, caller: Caller, document_id: UUID) -> DocumentProgress:
        """Return a persisted status projection; failed processing is still HTTP 200."""
        return project_progress(await self._visible_record(caller, document_id))

    async def get_document_detail(self, caller: Caller, document_id: UUID) -> DocumentDetail:
        """Authorize before generating a short-lived original read URL."""
        record = await self._visible_record(caller, document_id)
        assert record.job is not None
        invoice = None
        if record.job.status == "completed" and record.summary.doc_type == "commercial_invoice":
            if self.invoice_reader is None:
                raise IngestionError("INTERNAL_ERROR")
            invoice = await self.invoice_reader.get_invoice(caller, document_id)
            if invoice is None:
                raise IngestionError("INTERNAL_ERROR")
        url = await self.storage.sign(record.private_reference, caller.company_id, document_id)
        return DocumentDetail(**record.summary.model_dump(), job_id=record.job.id,
                              uploaded_by=record.uploaded_by, s3_url=url, invoice=invoice)

    async def list_documents(self, caller: Caller, query: ListQuery) -> tuple[list[DocumentSummary], Pagination]:
        """Use an already-filtered, consistently counted repository page."""
        page = await self.repository.list_documents(caller, query)
        if len(page.records) > query.page_size or page.total_records < len(page.records):
            raise IngestionError("INTERNAL_ERROR")
        if caller.role == "viewer" and any(row.status != "approved" for row in page.records):
            raise IngestionError("INTERNAL_ERROR")
        return list(page.records), Pagination.for_query(query, page.total_records)
