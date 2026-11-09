"""Stable errors; client messages never interpolate exception or request values."""
from .schemas import ErrorDetail

ERRORS: dict[str, tuple[int, str]] = {
    "AMBIGUOUS_AUTHENTICATION": (400, "Supply one authentication mechanism."),
    "UNAUTHORIZED": (401, "Authentication required."),
    "FORBIDDEN": (403, "You cannot upload documents."),
    "DOCUMENT_NOT_FOUND": (404, "Document not found."),
    "DUPLICATE_FILE_DETECTED": (409, "Matching file already exists."),
    "FILE_TOO_LARGE": (413, "File exceeds the upload size limit."),
    "UNSUPPORTED_FILE_TYPE": (415, "Unsupported or mismatched file format."),
    "VALIDATION_FAILED": (422, "Request validation failed."),
    "RATE_LIMIT_EXCEEDED": (429, "Request limit exceeded."),
    "STORAGE_UNAVAILABLE": (503, "Document storage is unavailable."),
    "DATABASE_UNAVAILABLE": (503, "Document database is unavailable."),
    "INTERNAL_ERROR": (500, "Internal server error."),
}


class IngestionError(Exception):
    def __init__(self, code: str, details: list[ErrorDetail] | None = None,
                 retry_after: int | None = None) -> None:
        self.status, self.message = ERRORS[code]
        self.code = code
        self.details = details or []
        self.retry_after = retry_after
        super().__init__(code)


def invalid(field: str, issue: str) -> IngestionError:
    return IngestionError("VALIDATION_FAILED", [ErrorDetail(field=field, issue=issue)])


def duplicate() -> IngestionError:
    return IngestionError("DUPLICATE_FILE_DETECTED", [ErrorDetail(
        field="file", issue="Matching file already exists; confirm to upload another copy."
    )])


class CommitUncertain(Exception):
    """Repository cannot yet prove whether its paired acceptance committed."""


class StaleClaim(Exception):
    """Current state/attempt/lease no longer authorizes this worker."""
