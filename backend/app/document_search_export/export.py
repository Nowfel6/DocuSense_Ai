"""Export command/query orchestration and canonical request hashing."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Callable, Protocol
from uuid import UUID

from .errors import SearchExportError, WorkerFailure
from .repository import (
    AcceptanceOutcome,
    ExportRepository,
    GeneratedArtifact,
    StorageProvider,
    TaskPublisher,
)
from .schemas import (
    Caller,
    CreateExportRequest,
    DirectExportRequest,
    DownloadGrant,
    ExportResource,
    ExportStatusResource,
    SearchCriteria,
)
from .settings import SearchExportSettings
from .storage import (
    require_private_object_key, signing_ttl, verify_artifact,
)


class ExportGenerator(Protocol):
    async def generate(self, resource: ExportResource, *, asynchronous: bool) -> GeneratedArtifact:
        """Revalidate, format, store, and return private terminal metadata."""
        ...


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def criteria_metadata(request: CreateExportRequest | DirectExportRequest) -> dict[str, object]:
    """Return bounded persistence-safe criteria with no query text or ID list."""
    if request.document_ids is not None:
        return {
            "selection_type": "document_ids",
            "requested_document_count": len(request.document_ids),
            "stable_sort": "explicit_request_order",
            "semantic_query_present": False,
        }
    assert request.criteria is not None
    payload = request.criteria.model_dump(mode="json", exclude_none=True)
    query = payload.pop("query", None)
    payload["selection_type"] = "criteria"
    payload["semantic_query_present"] = query is not None
    if query is not None:
        payload["semantic_query_sha256"] = _sha(str(query).encode("utf-8"))
    return payload


def request_hashes(
    request: CreateExportRequest | DirectExportRequest,
    idempotency_key: str | None,
    settings: SearchExportSettings,
) -> tuple[str, str, str | None]:
    metadata = criteria_metadata(request)
    encoded_metadata = _canonical_bytes(metadata)
    if len(encoded_metadata) > settings.criteria_json_max_bytes:
        raise SearchExportError("VALIDATION_FAILED")
    request_payload = {
        "schema_version": "docusense-approved-invoice-export-v1",
        "format": request.format,
        "selection": request.model_dump(mode="json", exclude_none=True),
    }
    return (
        _sha(encoded_metadata),
        _sha(_canonical_bytes(request_payload)),
        _sha(idempotency_key.encode("ascii")) if idempotency_key is not None else None,
    )


class ExportCommandService:
    def __init__(self, repository: ExportRepository, publisher: TaskPublisher,
                 generator: ExportGenerator, settings: SearchExportSettings) -> None:
        if any(value is None for value in (repository, publisher, generator, settings)):
            raise ValueError("Export command dependencies are mandatory")
        self._repository = repository
        self._publisher = publisher
        self._generator = generator
        self._settings = settings

    async def create(self, caller: Caller, request: CreateExportRequest,
                     idempotency_key: str | None) -> ExportResource:
        self._authorize(caller)
        self._validate_currency(request.criteria)
        criteria_hash, request_hash, key_hash = request_hashes(
            request, idempotency_key, self._settings
        )
        outcome = await self._repository.accept(
            caller, request, criteria_hash=criteria_hash, request_hash=request_hash,
            idempotency_key_hash=key_hash, allow_async=True,
        )
        if outcome.replayed:
            return outcome.resource
        if outcome.dispatch_required:
            try:
                await self._publisher.publish("exports.generate", outcome.resource.export_id)
            except Exception:
                # Durable queued state is authoritative; dispatcher recovery retries publish.
                pass
            return outcome.resource
        return await self._generate_synchronous(caller, outcome)

    async def create_direct(self, caller: Caller, request: DirectExportRequest) -> ExportResource:
        self._authorize(caller)
        self._validate_currency(request.criteria)
        criteria_hash, request_hash, _ = request_hashes(request, None, self._settings)
        outcome = await self._repository.accept(
            caller, request, criteria_hash=criteria_hash, request_hash=request_hash,
            idempotency_key_hash=None, allow_async=False,
        )
        if outcome.dispatch_required:
            raise SearchExportError("EXPORT_REQUIRES_ASYNC")
        if outcome.replayed:
            return outcome.resource
        return await self._generate_synchronous(caller, outcome)

    async def _generate_synchronous(self, caller: Caller,
                                    outcome: AcceptanceOutcome) -> ExportResource:
        resource = outcome.resource
        try:
            artifact = await self._generator.generate(resource, asynchronous=False)
            if not await self._repository.complete(resource.export_id, artifact):
                raise SearchExportError("EXPORT_DATA_INTEGRITY_ERROR")
        except WorkerFailure as exc:
            await self._repository.fail(resource.export_id, code=exc.code,
                                        message=exc.safe_message)
            public = exc.code if exc.code in {
                "EXPORT_SOURCE_CHANGED", "EXPORT_DATA_INTEGRITY_ERROR",
                "EXPORT_LIMIT_EXCEEDED", "EXPORT_STORAGE_UNAVAILABLE",
            } else "INTERNAL_ERROR"
            raise SearchExportError(public) from exc
        status = await self._repository.get_status(caller, resource.export_id)
        if status is None:
            raise SearchExportError("EXPORT_DATA_INTEGRITY_ERROR")
        return _resource(status)

    def _validate_currency(self, criteria: SearchCriteria | None) -> None:
        if criteria and criteria.currency is not None and (
            criteria.currency not in self._settings.supported_currencies
        ):
            raise SearchExportError("VALIDATION_FAILED")

    @staticmethod
    def _authorize(caller: Caller) -> None:
        if not caller.is_active:
            raise SearchExportError("UNAUTHORIZED")
        if caller.auth_kind != "bearer" or caller.role not in {"admin", "operator"}:
            raise SearchExportError("FORBIDDEN")


def _resource(status: ExportStatusResource) -> ExportResource:
    return ExportResource.model_validate(status.model_dump(exclude={"error_code", "error_message"}))


class ExportQueryService:
    def __init__(self, repository: ExportRepository, storage: StorageProvider,
                 settings: SearchExportSettings, *, stream_downloads: bool = True,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        if repository is None or storage is None or settings is None:
            raise ValueError("Export query dependencies are mandatory")
        self._repository = repository
        self._storage = storage
        self._settings = settings
        self._stream_downloads = stream_downloads
        self._clock = clock

    async def get_status(self, caller: Caller, export_id: UUID) -> ExportStatusResource:
        self._authorize(caller)
        value = await self._repository.get_status(caller, export_id)
        if value is None:
            raise SearchExportError("EXPORT_NOT_FOUND")
        return value

    async def authorize_download(self, caller: Caller, export_id: UUID,
                                 *, force_stream: bool = False) -> DownloadGrant:
        self._authorize(caller)
        record = await self._repository.get_download(caller, export_id)
        if record is None:
            raise SearchExportError("EXPORT_NOT_FOUND")
        if record.resource.status == "expired":
            raise SearchExportError("EXPORT_EXPIRED")
        if record.resource.status != "completed":
            raise SearchExportError("EXPORT_NOT_READY")
        now = self._clock().astimezone(timezone.utc)
        if record.expires_at is None or record.expires_at <= now:
            raise SearchExportError("EXPORT_EXPIRED")
        if any(value is None for value in (
            record.object_key, record.file_name, record.content_type,
            record.size_bytes, record.sha256,
        )):
            raise SearchExportError("EXPORT_DATA_INTEGRITY_ERROR")
        object_key = record.object_key
        assert object_key is not None and record.size_bytes is not None and record.sha256 is not None
        try:
            require_private_object_key(object_key, export_id)
        except WorkerFailure as exc:
            raise SearchExportError("EXPORT_DATA_INTEGRITY_ERROR") from exc
        try:
            verified = await self._storage.verify(
                object_key, record.size_bytes, record.sha256
            )
        except Exception as exc:
            raise SearchExportError("EXPORT_STORAGE_UNAVAILABLE") from exc
        if not verified:
            raise SearchExportError("EXPORT_DATA_INTEGRITY_ERROR")
        if self._stream_downloads or force_stream:
            try:
                body = await self._storage.read(object_key)
            except Exception as exc:
                raise SearchExportError("EXPORT_STORAGE_UNAVAILABLE") from exc
            if not verify_artifact(body, record.size_bytes, record.sha256):
                raise SearchExportError("EXPORT_DATA_INTEGRITY_ERROR")
            return DownloadGrant(
                kind="stream", file_name=record.file_name or "export",
                content_type=record.content_type or "application/octet-stream",
                content_length=record.size_bytes, sha256=record.sha256, body=body,
            )
        remaining = signing_ttl(
            now, record.expires_at, self._settings.signed_url_seconds
        )
        if remaining <= 0:
            raise SearchExportError("EXPORT_EXPIRED")
        try:
            url = await self._storage.sign(
                object_key, remaining
            )
        except Exception as exc:
            raise SearchExportError("EXPORT_STORAGE_UNAVAILABLE") from exc
        return DownloadGrant(
            kind="redirect", file_name=record.file_name or "export",
            content_type=record.content_type or "application/octet-stream",
            content_length=record.size_bytes, sha256=record.sha256, url=url,
        )

    @staticmethod
    def _authorize(caller: Caller) -> None:
        if not caller.is_active:
            raise SearchExportError("UNAUTHORIZED")
        if caller.auth_kind != "bearer" or caller.role not in {"admin", "operator"}:
            raise SearchExportError("FORBIDDEN")


__all__ = [
    "ExportCommandService", "ExportGenerator", "ExportQueryService",
    "criteria_metadata", "request_hashes",
]


