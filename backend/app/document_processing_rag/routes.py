"""FastAPI routes for restricted chunk and extraction-evidence reads."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Literal, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.responses import JSONResponse

from .errors import ApiError, invalid
from .schemas import (
    CallerContext, ChunkList, ChunkQuery, ErrorEnvelope, EvidenceQuery,
    EvidenceResponse,
)
from .service import RagReadService

logger = logging.getLogger("document_processing_rag")

ERROR_RESPONSES = {
    status: {"model": ErrorEnvelope, "description": description}
    for status, description in {
        400: "Ambiguous authentication.",
        401: "Authentication required.",
        403: "Technical data is not permitted for this role.",
        404: "Document not found.",
        409: "Processing has not completed.",
        422: "Invalid path or query fields.",
        429: "Request limit exceeded.",
        500: "Processing data is inconsistent or an internal error occurred.",
        503: "Document database is unavailable.",
    }.items()
}
CHUNK_QUERY_PARAMETERS = [
    {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}},
    {"name": "page_size", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}},
    {"name": "chunk_type", "in": "query", "schema": {"type": "string", "enum": ["text", "table", "header", "list", "image", "unknown"]}},
    {"name": "page_number", "in": "query", "schema": {"type": "integer", "minimum": 1}},
    {"name": "retrieval_role", "in": "query", "schema": {"type": "string", "enum": ["parent", "child", "both"]}},
    {"name": "section", "in": "query", "schema": {"type": "string", "minLength": 1, "maxLength": 255}},
    {"name": "sort_by", "in": "query", "schema": {"type": "string", "enum": ["ordinal"], "default": "ordinal"}},
    {"name": "order", "in": "query", "schema": {"type": "string", "enum": ["asc", "desc"], "default": "asc"}},
]
EVIDENCE_QUERY_PARAMETERS = [
    {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}},
    {"name": "page_size", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}},
    {"name": "field_path", "in": "query", "schema": {"type": "string", "minLength": 1, "maxLength": 255, "pattern": "^[a-z][a-z0-9_]*(?:\\.[A-Za-z0-9_-]+)+$"}},
    {"name": "validation_state", "in": "query", "schema": {"type": "string", "enum": ["valid", "invalid", "missing", "ambiguous", "unsupported"]}},
    {"name": "min_confidence", "in": "query", "schema": {"type": "number", "minimum": 0, "maximum": 100}},
]


@dataclass(frozen=True)
class Credential:
    kind: Literal["bearer", "api_key"]
    secret: str = field(repr=False)


class AuthResolver(Protocol):
    async def resolve(self, credential: Credential) -> CallerContext:
        ...


class RateLimiter(Protocol):
    async def check(self, caller: CallerContext) -> int | None:
        ...


def _credentials(request: Request) -> Credential:
    bearer = request.headers.getlist("authorization")
    keys = request.headers.getlist("x-api-key")
    if bearer and keys:
        raise ApiError("AMBIGUOUS_AUTHENTICATION")
    if len(bearer) > 1 or len(keys) > 1:
        raise ApiError("UNAUTHORIZED")
    if bearer:
        prefix, separator, token = bearer[0].partition(" ")
        if prefix.lower() != "bearer" or not separator or not token.strip() or " " in token.strip():
            raise ApiError("UNAUTHORIZED")
        return Credential("bearer", token.strip())
    if len(keys) == 1 and keys[0].strip():
        return Credential("api_key", keys[0].strip())
    raise ApiError("UNAUTHORIZED")


def _unique_query(request: Request) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in request.query_params.multi_items():
        if key in result:
            raise invalid("query", "Repeated query fields are not allowed.")
        result[key] = value
    return result


def _document_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise invalid("document_id", "Expected a UUID.") from exc


def _meta(request: Request) -> dict[str, str]:
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "request_id": request.state.rag_request_id}


class EnvelopeRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def wrapped(request: Request) -> Response:
            request.state.rag_request_id = f"req_{uuid4().hex}"
            try:
                return await handler(request)
            except RequestValidationError:
                error = invalid("request", "Invalid request fields.")
            except ApiError as exc:
                error = exc
            except Exception:
                logger.error("rag_internal_error request_id=%s", request.state.rag_request_id)
                error = ApiError("INTERNAL_ERROR")
            if error.status in (401, 403):
                logger.warning("rag_access_denied status=%s source_ip=%s request_id=%s",
                               error.status, request.client.host if request.client else "unknown",
                               request.state.rag_request_id)
            headers = {"Cache-Control": "no-store"}
            if error.retry_after is not None:
                headers["Retry-After"] = str(max(1, error.retry_after))
            body = {"success": False, "error": {"code": error.code, "message": error.message,
                    "details": [{"field": item.field, "issue": item.issue} for item in error.details]},
                    "meta": _meta(request)}
            return JSONResponse(body, status_code=error.status, headers=headers)

        return wrapped


def create_router(service: RagReadService, auth: AuthResolver, limiter: RateLimiter) -> APIRouter:
    if service is None or auth is None or limiter is None:
        raise ValueError("Service, shared auth, and rate limiter are mandatory")
    router = APIRouter(prefix="/api/v1/documents", tags=["documents"], route_class=EnvelopeRoute)

    async def caller_for(request: Request) -> CallerContext:
        caller = await auth.resolve(_credentials(request))
        retry_after = await limiter.check(caller)
        if retry_after is not None:
            raise ApiError("RATE_LIMIT_EXCEEDED", retry_after=retry_after)
        return caller

    @router.get("/{document_id}/chunks", response_model=ChunkList,
                responses=ERROR_RESPONSES,
                openapi_extra={"security": [{"BearerAuth": []}],
                               "parameters": CHUNK_QUERY_PARAMETERS})
    async def chunks(request: Request, response: Response, document_id: str) -> ChunkList:
        caller = await caller_for(request)
        try:
            query = ChunkQuery.model_validate(_unique_query(request))
        except ValidationError as exc:
            raise invalid("query", "Invalid chunk query fields.") from exc
        rows, pagination = await service.list_chunks(caller, _document_id(document_id), query)
        response.headers["Cache-Control"] = "no-store"
        return ChunkList(data=rows, pagination=pagination, message="Document chunks retrieved.", meta=_meta(request))

    @router.get("/{document_id}/extraction-evidence", response_model=EvidenceResponse,
                responses=ERROR_RESPONSES,
                openapi_extra={"security": [{"BearerAuth": []}],
                               "parameters": EVIDENCE_QUERY_PARAMETERS})
    async def evidence(request: Request, response: Response, document_id: str) -> EvidenceResponse:
        caller = await caller_for(request)
        try:
            query = EvidenceQuery.model_validate(_unique_query(request))
        except ValidationError as exc:
            raise invalid("query", "Invalid evidence query fields.") from exc
        data, pagination = await service.get_evidence(caller, _document_id(document_id), query)
        response.headers["Cache-Control"] = "no-store"
        return EvidenceResponse(data=data, pagination=pagination,
                                message="Extraction evidence retrieved.", meta=_meta(request))

    return router
