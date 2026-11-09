"""Fenced export generation, delivery recovery, retry, and expiry orchestration."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import pickle
import tempfile
from typing import BinaryIO, Callable, Iterator, Protocol
from uuid import UUID

from .errors import WorkerFailure
from .formatters import write_async_zip_stream, write_export
from .repository import (
    ExportInvoice, ExportRepository,
    GeneratedArtifact,
    StorageProvider,
    TaskPublisher,
    WorkerClaim,
)
from .schemas import ExportFormat, ExportResource
from .settings import SearchExportSettings
from .storage import require_private_object_key

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def retry_delay_seconds(attempt_count: int, jitter_seconds: int = 0) -> int:
    """Return the locked delay for claims one through three plus bounded jitter."""
    delays = {1: 30, 2: 120, 3: 480}
    if attempt_count not in delays:
        raise ValueError("Only attempts one through three may schedule retry")
    if not 0 <= jitter_seconds <= 15:
        raise ValueError("Retry jitter must be bounded to 0..15 seconds")
    return delays[attempt_count] + jitter_seconds


class WorkerGenerator(Protocol):
    async def generate_claim(self, claim: WorkerClaim) -> GeneratedArtifact:
        """Generate, verify, and promote one currently fenced async artifact."""
        ...


class ArtifactGenerator:
    """Shared sync/async generator using private storage and bounded disk spools."""

    def __init__(self, repository: ExportRepository, storage: StorageProvider,
                 settings: SearchExportSettings, clock: Clock = utc_now) -> None:
        if repository is None or storage is None or settings is None:
            raise ValueError("Generator dependencies are mandatory")
        self._repository = repository
        self._storage = storage
        self._settings = settings
        self._clock = clock

    async def generate(self, resource: ExportResource, *, asynchronous: bool) -> GeneratedArtifact:
        if asynchronous:
            raise ValueError("Async generation requires a worker claim")
        generated_at = resource.started_at or resource.created_at
        return await self._generate(
            source=resource.export_id,
            export_id=resource.export_id,
            format_name=resource.format,
            generated_at=generated_at,
            attempt=0,
            asynchronous=False,
            claim=None,
        )

    async def generate_claim(self, claim: WorkerClaim) -> GeneratedArtifact:
        return await self._generate(
            source=claim,
            export_id=claim.export_id,
            format_name=claim.format,
            generated_at=claim.generated_at,
            attempt=claim.attempt_count,
            asynchronous=True,
            claim=claim,
        )

    async def _generate(self, *, source: WorkerClaim | UUID, export_id: UUID,
                        format_name: ExportFormat, generated_at: datetime, attempt: int,
                        asynchronous: bool, claim: WorkerClaim | None) -> GeneratedArtifact:
        try:
            with tempfile.SpooledTemporaryFile(
                max_size=self._settings.spool_memory_max_bytes, mode="w+b"
            ) as source_spool:
                document_count = 0
                async for invoice in self._repository.source_stream(source):
                    pickle.dump(invoice, source_spool, protocol=5)
                    document_count += 1
                    if document_count > self._settings.export_document_max:
                        raise WorkerFailure("EXPORT_LIMIT_EXCEEDED", retryable=False)
                if document_count == 0:
                    raise WorkerFailure("EXPORT_DATA_INTEGRITY_ERROR", retryable=False)
                if claim is not None:
                    await self._progress(claim, "generating", 50)
                source_spool.seek(0)
                with tempfile.SpooledTemporaryFile(
                    max_size=self._settings.spool_memory_max_bytes, mode="w+b"
                ) as data_spool:
                    data_summary = await asyncio.to_thread(
                        write_export,
                        data_spool,
                        export_id,
                        generated_at,
                        format_name,
                        _read_pickled(source_spool),
                        row_limit=self._settings.export_row_max,
                        byte_limit=self._settings.export_uncompressed_max,
                    )
                    final_spool = data_spool
                    final_summary = data_summary
                    zip_spool = None
                    if asynchronous:
                        if claim is not None:
                            await self._progress(claim, "packaging", 70)
                        zip_spool = tempfile.SpooledTemporaryFile(
                            max_size=self._settings.spool_memory_max_bytes, mode="w+b"
                        )
                        final_summary = await asyncio.to_thread(
                            write_async_zip_stream, zip_spool, export_id,
                            generated_at, format_name, data_spool, data_summary,
                        )
                        final_spool = zip_spool
                    try:
                        if claim is not None:
                            await self._progress(claim, "storing", 80)
                        final_spool.seek(0)
                        staging_key = await self._storage.put_staging(
                            export_id, attempt, final_spool, final_summary.size_bytes,
                            final_summary.content_type, final_summary.sha256,
                        )
                        require_private_object_key(staging_key, export_id)
                        if not await self._storage.verify(
                            staging_key, final_summary.size_bytes, final_summary.sha256
                        ):
                            await self._storage.delete_exact(staging_key)
                            raise WorkerFailure("EXPORT_CHECKSUM_MISMATCH", retryable=True)
                        object_key = await self._storage.promote(
                            staging_key, export_id, final_summary.sha256
                        )
                        require_private_object_key(object_key, export_id)
                        if claim is not None:
                            await self._progress(claim, "storing", 95)
                        completed_at = self._clock().astimezone(timezone.utc)
                        return GeneratedArtifact(
                            file_name=final_summary.file_name,
                            content_type=final_summary.content_type,
                            size_bytes=final_summary.size_bytes,
                            sha256=final_summary.sha256,
                            document_count=final_summary.document_count,
                            row_count=final_summary.row_count,
                            object_key=object_key,
                            completed_at=completed_at,
                            expires_at=completed_at + timedelta(
                                seconds=self._settings.retention_seconds
                            ),
                        )
                    finally:
                        if zip_spool is not None:
                            zip_spool.close()
        except WorkerFailure:
            raise
        except Exception as exc:
            raise WorkerFailure("EXPORT_WORKER_INTERRUPTED", retryable=True) from exc

    async def _progress(self, claim: WorkerClaim, stage: str, percentage: int) -> None:
        if not await self._repository.progress(
            claim, stage=stage, percentage=percentage
        ):
            raise WorkerFailure("EXPORT_WORKER_INTERRUPTED", retryable=True)


def _read_pickled(source: BinaryIO) -> Iterator[ExportInvoice]:
    while True:
        try:
            value = pickle.load(source)
        except EOFError:
            return
        if not isinstance(value, ExportInvoice):
            raise WorkerFailure("EXPORT_DATA_INTEGRITY_ERROR", retryable=False)
        yield value


class ExportWorkerService:
    def __init__(self, repository: ExportRepository, generator: WorkerGenerator,
                 settings: SearchExportSettings, clock: Clock = utc_now,
                 jitter: Callable[[int], int] = lambda attempt: 0) -> None:
        if repository is None or generator is None or settings is None:
            raise ValueError("Worker dependencies are mandatory")
        self._repository = repository
        self._generator = generator
        self._settings = settings
        self._clock = clock
        self._jitter = jitter

    async def run(self, export_id: UUID) -> bool:
        """Claim and finish one task delivery; duplicates safely return false."""
        claim = await self._repository.claim(
            export_id, lease_seconds=self._settings.lease_seconds
        )
        if claim is None:
            return False
        heartbeat = asyncio.create_task(self._heartbeat(claim))
        generation = asyncio.create_task(self._generator.generate_claim(claim))
        try:
            done, _ = await asyncio.wait(
                {heartbeat, generation}, return_when=asyncio.FIRST_COMPLETED
            )
            if heartbeat in done:
                await heartbeat
            artifact = await generation
            if not await self._repository.complete(claim, artifact):
                raise WorkerFailure("EXPORT_WORKER_INTERRUPTED", retryable=True)
            return True
        except WorkerFailure as exc:
            if exc.retryable and claim.attempt_count < self._settings.max_attempts:
                delay = retry_delay_seconds(
                    claim.attempt_count, self._jitter(claim.attempt_count)
                )
                await self._repository.retry(
                    claim, code=exc.code, message=exc.safe_message,
                    due_at=self._clock() + timedelta(seconds=delay),
                )
            else:
                code = (
                    "EXPORT_ATTEMPTS_EXHAUSTED"
                    if exc.retryable else exc.code
                )
                message = (
                    "Export retry attempts were exhausted."
                    if exc.retryable else exc.safe_message
                )
                await self._repository.fail(claim, code=code, message=message)
            return False
        except Exception:
            if claim.attempt_count < self._settings.max_attempts:
                delay = retry_delay_seconds(
                    claim.attempt_count, self._jitter(claim.attempt_count)
                )
                await self._repository.retry(
                    claim, code="EXPORT_WORKER_INTERRUPTED",
                    message="Export worker was interrupted.",
                    due_at=self._clock() + timedelta(seconds=delay),
                )
            else:
                await self._repository.fail(
                    claim, code="EXPORT_ATTEMPTS_EXHAUSTED",
                    message="Export retry attempts were exhausted.",
                )
            return False
        finally:
            heartbeat.cancel()
            if not generation.done():
                generation.cancel()
            await asyncio.gather(heartbeat, generation, return_exceptions=True)

    async def _heartbeat(self, claim: WorkerClaim) -> None:
        while True:
            await asyncio.sleep(self._settings.heartbeat_seconds)
            if not await self._repository.renew(
                claim, lease_seconds=self._settings.lease_seconds
            ):
                raise WorkerFailure("EXPORT_WORKER_INTERRUPTED", retryable=True)


class ExportDispatcher:
    def __init__(self, repository: ExportRepository, publisher: TaskPublisher) -> None:
        self._repository = repository
        self._publisher = publisher

    async def dispatch_due(self, limit: int = 100) -> int:
        delivered = 0
        for export_id in await self._repository.due_dispatch(limit=max(1, min(limit, 1000))):
            try:
                await self._publisher.publish("exports.generate", export_id)
                delivered += 1
            except Exception:
                continue
        return delivered


class ExportExpiryService:
    def __init__(self, repository: ExportRepository, storage: StorageProvider) -> None:
        self._repository = repository
        self._storage = storage

    async def expire_due(self, limit: int = 100) -> int:
        expired = 0
        for export_id in await self._repository.due_expiry(limit=max(1, min(limit, 1000))):
            key = await self._repository.cleanup_key(export_id)
            if key is None:
                continue
            try:
                require_private_object_key(key, export_id)
                await self._storage.delete_exact(key)
            except Exception:
                continue
            if await self._repository.expire(export_id, key):
                expired += 1
        return expired


__all__ = [
    "ArtifactGenerator", "ExportDispatcher", "ExportExpiryService",
    "ExportWorkerService", "retry_delay_seconds", "utc_now",
]


