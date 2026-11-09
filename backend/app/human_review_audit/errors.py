"""Stable human-review errors with sanitized client messages."""
from .schemas import ErrorDetail

ERRORS: dict[str, tuple[int, str]] = {
    "AMBIGUOUS_AUTHENTICATION": (400, "Supply one authentication mechanism."),
    "UNAUTHORIZED": (401, "Authentication required."),
    "FORBIDDEN": (403, "Human review access is not permitted."),
    "DOCUMENT_NOT_FOUND": (404, "Document not found."),
    "DOCUMENT_NOT_REVIEWABLE": (409, "Document is not ready for review."),
    "INVALID_REVIEW_TRANSITION": (409, "Review action is not allowed from the current state."),
    "REVIEW_CONFLICT": (409, "A newer document review revision exists."),
    "IDEMPOTENCY_KEY_REUSED": (409, "Idempotency key was used for another request."),
    "VALIDATION_FAILED": (422, "Request validation failed."),
    "NO_REVIEW_CHANGES": (422, "Save requires at least one review change."),
    "APPROVAL_BLOCKED": (422, "Document does not satisfy approval requirements."),
    "RATE_LIMIT_EXCEEDED": (429, "Request limit exceeded."),
    "SOURCE_TEMPORARILY_UNAVAILABLE": (503, "Document source is temporarily unavailable."),
    "DATABASE_UNAVAILABLE": (503, "Review database is unavailable."),
    "REVIEW_DATA_INTEGRITY_ERROR": (500, "Review data is inconsistent."),
    "INTERNAL_ERROR": (500, "Internal server error."),
}


class ReviewError(Exception):
    def __init__(self, code: str, details: tuple[ErrorDetail, ...] = (),
                 retry_after: int | None = None) -> None:
        self.status, self.message = ERRORS[code]
        self.code = code
        self.details = details
        self.retry_after = retry_after
        super().__init__(code)


def invalid(field: str, issue: str) -> ReviewError:
    return ReviewError("VALIDATION_FAILED", (ErrorDetail(field=field, issue=issue),))
