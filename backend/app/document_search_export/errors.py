"""Stable Feature 05 errors with sanitized client messages."""
from __future__ import annotations

from .schemas import ErrorDetail

ERRORS: dict[str, tuple[int, str]] = {
    "AMBIGUOUS_AUTHENTICATION": (400, "Supply one authentication mechanism."),
    "UNAUTHORIZED": (401, "Authentication required."),
    "FORBIDDEN": (403, "Search or export access is not permitted."),
    "DOCUMENT_NOT_FOUND": (404, "Document not found."),
    "EXPORT_NOT_FOUND": (404, "Export not found."),
    "EXPORT_SELECTION_NOT_FOUND": (404, "One or more selected documents were not found."),
    "EXPORT_SOURCE_CHANGED": (409, "Approved source data changed; create a new export."),
    "EXPORT_NOT_READY": (409, "Export is not ready for download."),
    "IDEMPOTENCY_KEY_REUSED": (409, "Idempotency key was used for another request."),
    "EXPORT_EXPIRED": (410, "Export artifact has expired."),
    "VALIDATION_FAILED": (422, "Request validation failed."),
    "NO_EXPORTABLE_DOCUMENTS": (422, "No eligible approved documents were selected."),
    "EXPORT_SELECTION_NOT_ELIGIBLE": (422, "One or more selected documents are not eligible."),
    "EXPORT_REQUIRES_ASYNC": (422, "Selection requires the asynchronous export endpoint."),
    "EXPORT_LIMIT_EXCEEDED": (422, "Export exceeds an approved safety limit."),
    "RATE_LIMIT_EXCEEDED": (429, "Request limit exceeded."),
    "EXPORT_CONCURRENCY_LIMIT": (429, "Active export limit exceeded."),
    "SEARCH_CONFIGURATION_UNAVAILABLE": (503, "Search configuration is unavailable."),
    "SEARCH_PROVIDER_UNAVAILABLE": (503, "Semantic search is temporarily unavailable."),
    "EXPORT_STORAGE_UNAVAILABLE": (503, "Export storage is temporarily unavailable."),
    "SEARCH_DATA_INTEGRITY_ERROR": (500, "Search data is inconsistent."),
    "EXPORT_DATA_INTEGRITY_ERROR": (500, "Export source data is inconsistent."),
    "INTERNAL_ERROR": (500, "Internal server error."),
}

WORKER_ERROR_MESSAGES: dict[str, str] = {
    "EXPORT_SOURCE_CHANGED": "Approved source data changed.",
    "EXPORT_DATA_INTEGRITY_ERROR": "Export source data is inconsistent.",
    "EXPORT_LIMIT_EXCEEDED": "Export exceeded a safety limit.",
    "EXPORT_FORMATTER_FAILED": "Export formatting failed.",
    "EXPORT_STORAGE_UNAVAILABLE": "Export storage was unavailable.",
    "EXPORT_DATABASE_UNAVAILABLE": "Export database was unavailable.",
    "EXPORT_WORKER_INTERRUPTED": "Export worker was interrupted.",
    "EXPORT_CHECKSUM_MISMATCH": "Export artifact verification failed.",
    "EXPORT_ATTEMPTS_EXHAUSTED": "Export retry attempts were exhausted.",
}


class SearchExportError(Exception):
    """Expected public error with no raw provider/database/storage detail."""

    def __init__(
        self,
        code: str,
        details: tuple[ErrorDetail, ...] = (),
        retry_after: int | None = None,
    ) -> None:
        self.status, self.message = ERRORS[code]
        self.code = code
        self.details = details
        self.retry_after = retry_after
        super().__init__(code)


class WorkerFailure(Exception):
    """Sanitized worker failure classification."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        if code not in WORKER_ERROR_MESSAGES:
            raise ValueError("Unknown worker error code")
        self.code = code
        self.safe_message = WORKER_ERROR_MESSAGES[code]
        self.retryable = retryable
        super().__init__(code)


def invalid(field: str, issue: str) -> SearchExportError:
    return SearchExportError(
        "VALIDATION_FAILED",
        (ErrorDetail(field=field[:100], issue=issue[:300]),),
    )


__all__ = ["ERRORS", "SearchExportError", "WorkerFailure", "invalid"]


