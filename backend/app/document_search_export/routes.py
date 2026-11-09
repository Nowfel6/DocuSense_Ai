"""Feature 05 FastAPI routes with injected auth, limits, and services."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Literal, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.responses import JSONResponse, RedirectResponse

from .errors import SearchExportError, invalid
from .export import ExportCommandService, ExportQueryService
from .schemas import (
    Caller,
    CreateExportRequest,
    DirectExportRequest,
    DocumentSearchRequest,
    ErrorBody,
    ErrorEnvelope,
    ExportResource,
    ExportStatusResource,
    IdempotencyHeader,
    Meta,
    SearchSuccess,
    Success,
)
from .search import SearchService

logger = logging.getLogger("document_search_export")
PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
}


@dataclass(frozen=True)
class Credential:
    kind: Literal["bearer", "api_key"]
    secret: str = field(repr=False)


class AuthResolver(Protocol):
    async def resolve(self, credential: Credential) -> Caller:
        """Validate one credential and return persisted active actor context."""
        ...


class RateLimiter(Protocol):
    async def check(self, caller: Caller, operation: str) -> int | None:
        """Apply separate atomic user/company buckets and return Retry-After."""
        ...


def _credentials(request: Request) -> Credential:
    bearer = request.headers.getlist("authorization")
    keys = request.headers.getlist("x-api-key")
    if bearer and keys:
        raise SearchExportError("AMBIGUOUS_AUTHENTICATION")
    if len(bearer) > 1 or len(keys) > 1:
        raise SearchExportError("UNAUTHORIZED")
    if bearer:
        prefix, separator, token = bearer[0].partition(" ")
        clean = token.strip()
        if prefix.lower() != "bearer" or not separator or not clean or " " in clean:
            raise SearchExportError("UNAUTHORIZED")
        return Credential("bearer", clean)
    if keys and keys[0].strip():
        return Credential("api_key", keys[0].strip())
    raise SearchExportError("UNAUTHORIZED")


def _meta(request: Request) -> Meta:
    return Meta(timestamp=datetime.now(timezone.utc),
                request_id=request.state.dse_request_id)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


async def _json(request: Request, maximum: int) -> object:
    values = request.headers.getlist("content-length")
    if len(values) > 1:
        raise invalid("content-length", "Repeated Content-Length is not allowed.")
    if values:
        try:
            length = int(values[0])
            if length < 0 or length > maximum:
                raise invalid("body", "Request body is too large.")
        except ValueError as exc:
            raise invalid("content-length", "Invalid Content-Length.") from exc
    body = await request.body()
    if not body or len(body) > maximum:
        raise invalid("body", "Missing or oversized JSON body.")
    try:
        return json.loads(body.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise invalid("body", "Invalid JSON body.") from exc


def _path(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except (ValueError, AttributeError) as exc:
        raise invalid(field_name, "Expected a UUID.") from exc


def _direct_query(request: Request) -> DirectExportRequest:
    scalar: dict[str, str] = {}
    document_ids: list[str] = []
    statuses: list[str] = []
    allowed = {
        "format", "document_id", "query", "document_statuses", "document_type",
        "supplier", "currency", "invoice_date_from", "invoice_date_to",
        "uploaded_from", "uploaded_to", "min_total", "max_total", "sort_by",
        "order",
    }
    for key, value in request.query_params.multi_items():
        if key not in allowed:
            raise invalid("query", "Unknown direct-export query field.")
        if key == "document_id":
            document_ids.append(value)
        elif key == "document_statuses":
            statuses.append(value)
        elif key in scalar:
            raise invalid(key, "Repeated scalar query field is not allowed.")
        else:
            scalar[key] = value
    if "query" in scalar:
        raise invalid("query", "Direct export does not accept semantic query.")
    format_name = scalar.pop("format", None)
    payload: dict[str, object] = {"format": format_name}
    if document_ids:
        if scalar or statuses:
            raise invalid("selection", "Do not combine document IDs and criteria.")
        payload["document_ids"] = document_ids
    else:
        criteria_payload: dict[str, object] = dict(scalar)
        if statuses:
            criteria_payload["document_statuses"] = statuses
        payload["criteria"] = criteria_payload
    try:
        return DirectExportRequest.model_validate(payload)
    except ValidationError as exc:
        raise invalid("query", "Invalid direct-export query.") from exc


class EnvelopeRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def wrapped(request: Request) -> Response:
            request.state.dse_request_id = f"req_{uuid4().hex}"
            try:
                response = await handler(request)
                for key, value in PRIVATE_HEADERS.items():
                    response.headers.setdefault(key, value)
                return response
            except RequestValidationError:
                error = invalid("request", "Invalid request fields.")
            except SearchExportError as exc:
                error = exc
            except Exception:
                logger.error("dse_internal_error request_id=%s",
                             request.state.dse_request_id)
                error = SearchExportError("INTERNAL_ERROR")
            if error.status in (401, 403):
                logger.warning(
                    "dse_access_denied status=%s source_ip=%s request_id=%s",
                    error.status,
                    request.client.host if request.client else "unknown",
                    request.state.dse_request_id,
                )
            headers = dict(PRIVATE_HEADERS)
            if error.retry_after is not None:
                headers["Retry-After"] = str(max(1, error.retry_after))
            envelope = ErrorEnvelope(
                error=ErrorBody(code=error.code, message=error.message,
                                details=error.details),
                meta=_meta(request),
            )
            return JSONResponse(envelope.model_dump(mode="json"),
                                status_code=error.status, headers=headers)

        return wrapped


def create_router(search: SearchService, commands: ExportCommandService,
                  queries: ExportQueryService, auth: AuthResolver,
                  limiter: RateLimiter, *, body_max_bytes: int = 4 * 1024 * 1024) -> APIRouter:
    """Create Feature 05 routes only when every shared dependency is supplied."""
    if any(value is None for value in (search, commands, queries, auth, limiter)):
        raise ValueError("Search/export services, auth, and limiter are mandatory")
    router = APIRouter(prefix="/api/v1", tags=["document-search-export"],
                       route_class=EnvelopeRoute)

    async def caller_for(request: Request, operation: str) -> Caller:
        caller = await auth.resolve(_credentials(request))
        retry_after = await limiter.check(caller, operation)
        if retry_after is not None:
            raise SearchExportError("RATE_LIMIT_EXCEEDED", retry_after=retry_after)
        return caller

    @router.post("/documents/search", response_model=SearchSuccess)
    async def search_documents(request: Request) -> SearchSuccess:
        caller = await caller_for(request, "search")
        try:
            payload = DocumentSearchRequest.model_validate(
                await _json(request, body_max_bytes)
            )
        except ValidationError as exc:
            raise invalid("body", "Invalid search request.") from exc
        items, pagination = await search.search(caller, payload)
        return SearchSuccess(
            data=items, pagination=pagination, message="Document search completed.",
            meta=_meta(request),
        )

    @router.get("/documents/export", response_model=None)
    async def direct_export(request: Request) -> Response:
        caller = await caller_for(request, "export_create")
        resource = await commands.create_direct(caller, _direct_query(request))
        grant = await queries.authorize_download(
            caller, resource.export_id, force_stream=True
        )
        assert grant.body is not None
        headers = dict(PRIVATE_HEADERS)
        headers.update({
            "Content-Disposition": f'attachment; filename="{grant.file_name}"',
            "Content-Type": grant.content_type,
            "X-Export-Id": str(resource.export_id),
            "X-Content-SHA256": grant.sha256,
        })
        return Response(content=grant.body, headers=headers)

    @router.post("/exports", response_model=Success[ExportResource])
    async def create_export(request: Request) -> Response:
        caller = await caller_for(request, "export_create")
        keys = request.headers.getlist("idempotency-key")
        if len(keys) > 1:
            raise invalid("Idempotency-Key", "Repeated header is not allowed.")
        key = None
        if keys:
            try:
                key = IdempotencyHeader(value=keys[0]).value
            except ValidationError as exc:
                raise invalid("Idempotency-Key", "Invalid idempotency key.") from exc
        try:
            payload = CreateExportRequest.model_validate(
                await _json(request, body_max_bytes)
            )
        except ValidationError as exc:
            raise invalid("body", "Invalid export request.") from exc
        data = await commands.create(caller, payload, key)
        envelope = Success(
            data=data,
            message="Export completed." if data.status == "completed" else "Export accepted.",
            meta=_meta(request),
        )
        status_code = 201 if data.status == "completed" else 202
        return JSONResponse(envelope.model_dump(mode="json"), status_code=status_code,
                            headers=PRIVATE_HEADERS)

    @router.get("/exports/{export_id}/download", response_model=None)
    async def download_export(request: Request, export_id: str) -> Response:
        caller = await caller_for(request, "export_download")
        grant = await queries.authorize_download(caller, _path(export_id, "export_id"))
        headers = dict(PRIVATE_HEADERS)
        headers.update({
            "Content-Disposition": f'attachment; filename="{grant.file_name}"',
            "Content-Type": grant.content_type,
            "X-Content-SHA256": grant.sha256,
        })
        if grant.kind == "redirect":
            assert grant.url is not None
            return RedirectResponse(grant.url, status_code=302, headers=headers)
        assert grant.body is not None
        return Response(content=grant.body, headers=headers)

    @router.get("/exports/{export_id}", response_model=Success[ExportStatusResource])
    async def export_status(request: Request, export_id: str) -> Success[ExportStatusResource]:
        caller = await caller_for(request, "export_status")
        data = await queries.get_status(caller, _path(export_id, "export_id"))
        return Success(data=data, message="Export status loaded.", meta=_meta(request))

    return router


__all__ = ["AuthResolver", "Credential", "RateLimiter", "create_router"]


