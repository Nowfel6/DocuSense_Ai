"""Authorized private source-view adapter for human review."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

from ..human_review_audit.errors import ReviewError
from ..human_review_audit.schemas import Caller, SourceView


class PrivateObjectStore(Protocol):
    async def sign(self, reference: str, company_id: UUID, document_id: UUID) -> str: ...


class ReviewSourceAccess:
    def __init__(self, storage: PrivateObjectStore) -> None:
        if storage is None:
            raise ValueError("Private object storage is required")
        self._storage = storage

    async def issue(
        self,
        caller: Caller,
        document_id: UUID,
        private_reference: str,
        mime_type: str,
        page_count: int | None,
    ) -> SourceView:
        if caller.user_id is None or caller.role not in {"admin", "operator", "viewer"}:
            raise ReviewError("FORBIDDEN")
        try:
            url = await self._storage.sign(private_reference, caller.company_id, document_id)
            return SourceView(
                url=url,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=300),
                mime_type=mime_type,
                page_count=page_count,
            )
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError("SOURCE_TEMPORARILY_UNAVAILABLE") from exc


__all__ = ["ReviewSourceAccess"]

