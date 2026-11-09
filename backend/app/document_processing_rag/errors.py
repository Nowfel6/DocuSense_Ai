"""Stable domain and HTTP-safe errors for document processing."""
from dataclasses import dataclass


HTTP_ERRORS: dict[str, tuple[int, str]] = {
    "AMBIGUOUS_AUTHENTICATION": (400, "Supply one authentication mechanism."),
    "UNAUTHORIZED": (401, "Authentication required."),
    "FORBIDDEN": (403, "Technical document data is restricted."),
    "DOCUMENT_NOT_FOUND": (404, "Document not found."),
    "PROCESSING_NOT_COMPLETE": (409, "Document processing has not completed the required stage."),
    "VALIDATION_FAILED": (422, "Request validation failed."),
    "RATE_LIMIT_EXCEEDED": (429, "Request limit exceeded."),
    "DATABASE_UNAVAILABLE": (503, "Document database is unavailable."),
    "PROCESSING_DATA_INTEGRITY_ERROR": (500, "Processing data is inconsistent."),
    "INTERNAL_ERROR": (500, "Internal server error."),
}

PROCESSING_CODES = frozenset({
    "SOURCE_OBJECT_UNAVAILABLE", "PDF_ENCRYPTED_OR_CORRUPT",
    "OCR_UNSUPPORTED_LANGUAGE", "PARSER_FAILED", "CHUNKING_FAILED",
    "EMBEDDING_CONFIGURATION_MISMATCH", "EMBEDDING_PROVIDER_UNAVAILABLE",
    "VECTOR_INDEXING_FAILED", "INSUFFICIENT_EXTRACTION_EVIDENCE",
    "INVALID_STRUCTURED_OUTPUT", "UNSUPPORTED_EXTRACTION_TYPE",
    "PROCESSING_CONFIGURATION_CHANGED", "PROCESSING_TIMEOUT",
    "PROCESSING_DATA_INTEGRITY_ERROR", "PROCESSING_FAILED",
    "LLM_RATE_LIMITED",
})

TERMINAL_CODES = frozenset({
    "PDF_ENCRYPTED_OR_CORRUPT", "OCR_UNSUPPORTED_LANGUAGE",
    "UNSUPPORTED_EXTRACTION_TYPE", "EMBEDDING_CONFIGURATION_MISMATCH",
    "INSUFFICIENT_EXTRACTION_EVIDENCE", "INVALID_STRUCTURED_OUTPUT",
    "PROCESSING_CONFIGURATION_CHANGED", "PROCESSING_DATA_INTEGRITY_ERROR",
})


class ProcessingError(Exception):
    """A stable processing failure whose raw provider cause is never exposed."""

    def __init__(self, code: str) -> None:
        if code not in PROCESSING_CODES:
            code = "PROCESSING_FAILED"
        self.code = code
        super().__init__(code)

    @property
    def retryable(self) -> bool:
        return self.code not in TERMINAL_CODES


@dataclass(frozen=True)
class ErrorDetail:
    field: str
    issue: str


class ApiError(Exception):
    def __init__(self, code: str, details: tuple[ErrorDetail, ...] = (), retry_after: int | None = None) -> None:
        self.status, self.message = HTTP_ERRORS[code]
        self.code = code
        self.details = details
        self.retry_after = retry_after
        super().__init__(code)


def invalid(field: str, issue: str) -> ApiError:
    return ApiError("VALIDATION_FAILED", (ErrorDetail(field, issue),))


class FenceLost(Exception):
    """The database no longer authorizes this attempt/fence."""
