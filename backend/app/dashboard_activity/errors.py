"""Stable Feature 06 errors with sanitized client messages."""
from __future__ import annotations

from .schemas import ErrorDetail

ERRORS: dict[str, tuple[int, str]] = {
    "AMBIGUOUS_AUTHENTICATION": (400, "Supply one authentication mechanism."),
    "UNAUTHORIZED": (401, "Authentication required."),
    "FORBIDDEN": (403, "Dashboard access is not permitted."),
    "VALIDATION_FAILED": (422, "Request validation failed."),
    "RATE_LIMIT_EXCEEDED": (429, "Request limit exceeded."),
    "ANALYTICS_SOURCE_UNAVAILABLE": (503, "Analytics sources are temporarily unavailable."),
    "ANALYTICS_DATA_INTEGRITY_ERROR": (500, "Analytics source data is inconsistent."),
}


class DashboardActivityError(Exception):
    """Expected public error carrying no raw database or input detail."""

    def __init__(
        self,
        code: str,
        details: tuple[ErrorDetail, ...] = (),
        retry_after: int | None = None,
    ) -> None:
        try:
            self.status, self.message = ERRORS[code]
        except KeyError as exc:
            raise ValueError("Unknown dashboard/activity error code") from exc
        self.code = code
        self.details = details
        self.retry_after = retry_after
        super().__init__(code)


def invalid(field: str, issue: str) -> DashboardActivityError:
    return DashboardActivityError(
        "VALIDATION_FAILED",
        (ErrorDetail(field=field[:100], issue=issue[:300]),),
    )


__all__ = ["DashboardActivityError", "ERRORS", "invalid"]
