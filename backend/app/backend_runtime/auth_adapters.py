"""Feature-specific caller adapters over the verified shared auth resolver."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from .auth import AuthFailure, AuthIdentity, SharedAuthResolver
from ..dashboard_activity.errors import DashboardActivityError
from ..dashboard_activity.schemas import Caller as DashboardCaller
from ..document_ingestion.errors import IngestionError
from ..document_ingestion.schemas import Caller as IngestionCaller
from ..document_processing_rag.errors import ApiError
from ..document_processing_rag.schemas import CallerContext as RagCaller
from ..document_search_export.errors import SearchExportError
from ..document_search_export.schemas import Caller as SearchExportCaller
from ..human_review_audit.errors import ReviewError
from ..human_review_audit.schemas import Caller as ReviewCaller


CallerT = TypeVar("CallerT")


class _AuthAdapter:
    def __init__(self, resolver: SharedAuthResolver) -> None:
        if resolver is None:
            raise ValueError("Shared auth resolver is required")
        self._resolver = resolver

    async def _resolve(
        self,
        credential: Any,
        caller_factory: Callable[..., CallerT],
        error_factory: Callable[[str], Exception],
        *,
        human_only: bool = False,
    ) -> CallerT:
        try:
            identity: AuthIdentity = await self._resolver.resolve_identity(credential)
        except AuthFailure as exc:
            # Feature route wrappers understand their own sanitized domain errors.
            raise error_factory("UNAUTHORIZED") from exc
        if human_only and identity.user_id is None:
            raise error_factory("FORBIDDEN")
        return caller_factory(
            company_id=identity.company_id,
            user_id=identity.user_id,
            role=identity.role,
            **({} if human_only else {"api_key_id": identity.api_key_id}),
        )


class IngestionAuthAdapter(_AuthAdapter):
    async def resolve(self, credential: Any) -> IngestionCaller:
        return await self._resolve(credential, IngestionCaller, IngestionError)


class RagAuthAdapter(_AuthAdapter):
    async def resolve(self, credential: Any) -> RagCaller:
        return await self._resolve(credential, RagCaller, ApiError)


class ReviewAuthAdapter(_AuthAdapter):
    async def resolve(self, credential: Any) -> ReviewCaller:
        return await self._resolve(credential, ReviewCaller, ReviewError)


class SearchExportAuthAdapter(_AuthAdapter):
    async def resolve(self, credential: Any) -> SearchExportCaller:
        # Feature 5 is deliberately human-only; its caller schema has no API-key shape.
        return await self._resolve(
            credential,
            SearchExportCaller,
            SearchExportError,
            human_only=True,
        )


class DashboardAuthAdapter(_AuthAdapter):
    async def resolve(self, credential: Any) -> DashboardCaller:
        """Resolve Feature 06 identities and reject API keys after authentication."""
        return await self._resolve(
            credential,
            DashboardCaller,
            DashboardActivityError,
            human_only=True,
        )


__all__ = [
    "DashboardAuthAdapter",
    "IngestionAuthAdapter",
    "RagAuthAdapter",
    "ReviewAuthAdapter",
    "SearchExportAuthAdapter",
]
