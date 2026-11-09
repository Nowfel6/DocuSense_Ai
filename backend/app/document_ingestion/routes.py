"""FastAPI router factory; verified auth, rate limiting and repository are REQUIRED."""
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Literal, Protocol
from uuid import uuid4

from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.responses import JSONResponse

from .errors import IngestionError, invalid
from .schemas import (
    Caller, DocumentDetail, DocumentList, DocumentPath, DocumentProgress, ErrorBody,
    ErrorEnvelope, ListQuery, Meta, Success, UploadAccepted,
)
from .service import IngestionService
from .validation import parse_upload, unique_fields

logger = logging.getLogger("document_ingestion")

STATUS_ERROR_RESPONSES = {
    status: {"model": ErrorEnvelope, "description": description}
    for status, description in {
        400: "Ambiguous authentication.",
        401: "Authentication required.",
        404: "Document not found.",
        422: "Invalid document identifier or query fields.",
        429: "Request limit exceeded.",
        500: "Internal server error.",
        503: "Document database is unavailable.",
    }.items()
}


@dataclass(frozen=True)
class Credential:
    kind: Literal["bearer", "api_key"]
    secret: str = field(repr=False)


class AuthResolver(Protocol):
    async def resolve(self, credential: Credential) -> Caller:
        """Shared verified auth must enforce issuer/expiry, identity, tenant and activity."""
        ...


class RateLimiter(Protocol):
    async def check(self, caller: Caller) -> int | None:
        """Atomic shared budget, default 60/minute; return Retry-After if denied."""
        ...


def credentials(request: Request) -> Credential:
    bearer = request.headers.getlist("authorization")
    keys = request.headers.getlist("x-api-key")
    if bearer and keys:
        raise IngestionError("AMBIGUOUS_AUTHENTICATION")
    if len(bearer) > 1 or len(keys) > 1:
        raise IngestionError("UNAUTHORIZED")
    if bearer:
        prefix, separator, token = bearer[0].partition(" ")
        if prefix.lower() != "bearer" or not separator or not token.strip() or " " in token.strip():
            raise IngestionError("UNAUTHORIZED")
        return Credential("bearer", token.strip())
    if keys and keys[0].strip():
        return Credential("api_key", keys[0].strip())
    raise IngestionError("UNAUTHORIZED")


def metadata(request: Request) -> Meta:
    return Meta(timestamp=datetime.now(timezone.utc), request_id=request.state.ingestion_request_id)


class EnvelopeRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def wrapped(request: Request) -> Response:
            request.state.ingestion_request_id = f"req_{uuid4().hex}"
            try:
                return await handler(request)
            except RequestValidationError:
                error = invalid("request", "Invalid request fields.")
            except IngestionError as exc:
                error = exc
            except Exception:
                # Do not log untrusted exception text or upload/provider content.
                logger.error("ingestion_internal_error request_id=%s", request.state.ingestion_request_id)
                error = IngestionError("INTERNAL_ERROR")
            if error.status in (401, 403):
                logger.warning("ingestion_access_denied status=%s source_ip=%s request_id=%s",
                               error.status, request.client.host if request.client else "unknown",
                               request.state.ingestion_request_id)
            headers = {"Cache-Control": "no-store"}
            if error.retry_after is not None:
                headers["Retry-After"] = str(max(1, error.retry_after))
            envelope = ErrorEnvelope(error=ErrorBody(code=error.code, message=error.message,
                                                     details=error.details), meta=metadata(request))
            return JSONResponse(envelope.model_dump(mode="json"), status_code=error.status, headers=headers)

        return wrapped


def create_router(
    service: IngestionService,
    auth: AuthResolver,
    limiter: RateLimiter,
    *,
    include_detail: bool = True,
) -> APIRouter:
    """Create four routes only when the host explicitly supplies all dependencies.

    This function does not resolve credentials itself, supply fake dependencies,
    configure a database, run migrations, or expose an unauthenticated fallback.
    """
    if service is None or auth is None or limiter is None:
        raise ValueError("Service, shared auth and rate limiter are mandatory")
    router = APIRouter(prefix="/api/v1/documents", tags=["documents"], route_class=EnvelopeRoute)

    async def caller_for(request: Request, upload: bool = False) -> Caller:
        caller = await auth.resolve(credentials(request))
        if upload and caller.role == "viewer":
            raise IngestionError("FORBIDDEN")
        retry_after = await limiter.check(caller)
        if retry_after is not None:
            raise IngestionError("RATE_LIMIT_EXCEEDED", retry_after=retry_after)
        return caller

    def no_query(request: Request) -> None:
        if request.query_params:
            raise invalid("query", "This route does not accept query fields.")

    def document_path(document_id: str) -> DocumentPath:
        try:
            return DocumentPath(document_id=document_id)
        except ValidationError as exc:
            raise invalid("document_id", "Expected a UUID.") from exc

    @router.post("/upload", status_code=202, response_model=Success[UploadAccepted],
                 openapi_extra={"requestBody": {"required": True, "content": {
                     "multipart/form-data": {"schema": {"type": "object", "required": ["file"],
                         "additionalProperties": False, "properties": {
                             "file": {"type": "string", "format": "binary"},
                             "doc_type_hint": {"type": "string", "enum": ["commercial_invoice", "purchase_order", "packing_list", "invoice", "po"], "default": "commercial_invoice"},
                             "confirm_duplicate": {"type": "boolean", "default": False}}}}}}})
    async def upload(request: Request) -> Success[UploadAccepted]:
        caller = await caller_for(request, upload=True)
        no_query(request)
        original, form = await parse_upload(request.headers, request.stream(),
                                            service.timing.upload_receive_timeout_seconds)
        try:
            accepted = await asyncio.wait_for(service.accept_upload(caller, original, form),
                                              service.timing.acceptance_deadline_seconds)
        except asyncio.TimeoutError as exc:
            raise IngestionError("DATABASE_UNAVAILABLE") from exc
        return Success[UploadAccepted](data=accepted,
            message="Document uploaded successfully and queued for processing.", meta=metadata(request))

    @router.get("/{document_id}/status", response_model=Success[DocumentProgress],
                responses=STATUS_ERROR_RESPONSES,
                openapi_extra={"security": [
                    {"BearerAuth": []}, {"ApiKeyAuth": []},
                ]})
    async def status(request: Request, document_id: str) -> Success[DocumentProgress]:
        caller = await caller_for(request)
        no_query(request)
        data = await service.get_progress(caller, document_path(document_id).document_id)
        return Success[DocumentProgress](data=data, message="Document status retrieved.", meta=metadata(request))

    @router.get("", response_model=DocumentList)
    async def listing(request: Request) -> DocumentList:
        caller = await caller_for(request)
        try:
            query = ListQuery.model_validate(unique_fields(request.query_params.multi_items()))
        except ValidationError as exc:
            raise invalid("query", "Invalid document query fields.") from exc
        rows, pagination = await service.list_documents(caller, query)
        return DocumentList(data=rows, pagination=pagination, message="Documents retrieved.", meta=metadata(request))

    if include_detail:
        @router.get("/{document_id}", response_model=Success[DocumentDetail])
        async def detail(request: Request, response: Response, document_id: str) -> Success[DocumentDetail]:
            caller = await caller_for(request)
            no_query(request)
            data = await service.get_document_detail(caller, document_path(document_id).document_id)
            response.headers["Cache-Control"] = "no-store"
            return Success[DocumentDetail](data=data, message="Document retrieved.", meta=metadata(request))

    return router
