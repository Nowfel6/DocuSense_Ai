"""Security checks shared by concrete private-storage adapters."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from uuid import UUID

from .errors import WorkerFailure

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def require_private_object_key(object_key: str, export_id: UUID) -> str:
    """Validate one exact tenant/export-scoped key without accepting prefixes."""
    if (
        not object_key
        or object_key.startswith(("/", "\\"))
        or "\\" in object_key
        or _CONTROL.search(object_key)
    ):
        raise WorkerFailure("EXPORT_DATA_INTEGRITY_ERROR", retryable=False)
    parts = object_key.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise WorkerFailure("EXPORT_DATA_INTEGRITY_ERROR", retryable=False)
    identifiers = {str(export_id), export_id.hex}
    if not any(identifier in object_key for identifier in identifiers):
        raise WorkerFailure("EXPORT_DATA_INTEGRITY_ERROR", retryable=False)
    return object_key


def verify_artifact(data: bytes, expected_size: int, expected_sha256: str) -> bool:
    """Compare exact bytes with the persisted positive size and SHA-256."""
    return (
        expected_size > 0
        and len(data) == expected_size
        and hashlib.sha256(data).hexdigest() == expected_sha256
    )


def signing_ttl(now: datetime, expires_at: datetime, configured_seconds: int) -> int:
    """Return a positive TTL bounded by five minutes and artifact retention."""
    current = now.astimezone(timezone.utc)
    expiry = expires_at.astimezone(timezone.utc)
    remaining = int((expiry - current).total_seconds())
    if remaining <= 0:
        return 0
    return min(300, configured_seconds, remaining)


__all__ = ["require_private_object_key", "signing_ttl", "verify_artifact"]


