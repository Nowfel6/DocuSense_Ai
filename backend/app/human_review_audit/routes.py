"""FastAPI routes; shared auth, limiter, repositories, and source access are required."""
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
from starlette.responses import JSONResponse

from .errors import ReviewError, invalid
from .schemas import (
    AuditLogResponse,
    AuditQuery,
    Caller,
    ErrorBody,
    ErrorEnvelope,
    IdempotencyHeader,
    Meta,
    MutationData,
    PreviewData,
    REVIEW_ACTION_ADAPTER,
    ReviewDetail,
    ReviewValidationRequest,
    Success,
)
from .service import (
    ReviewCommandService,
    ReviewQueryService,
    ReviewValidationService,
)

logger = logging.getLogger("human_review_audit")
MAX_JSON_BODY_BYTES = 20 * 1024 * 1024

DETAIL_ERROR_RESPONSES = {
    status: {"model": ErrorEnvelope, "description": description}
    for status, description in {
        400: "Ambiguous authentication.",
        401: "Authentication required.",
        403: "Document detail is not permitted for this caller.",
        404: "Document not found or not visible to this caller.",
        409: "A terminal review projection is incomplete.",
        422: "Invalid document identifier or query fields.",
        429: "Request limit exceeded.",
        500: "Document data is inconsistent or an internal error occurred.",
        503: "Document data or source storage is unavailable.",
    }.items()
}


@dataclass(frozen=True)
class Credential:
    kind: Literal["bearer", "api_key"]
    secret: str = field(repr=False)


class AuthResolver(Protocol):
    async def resolve(self, credential: Credential) -> Caller:
        """Shared auth validates token/key, issuer/expiry, actor, company, and role."""
        ...


class RateLimiter(Protocol):
    async def check(self, caller: Caller) -> int | None:
        """Atomic user/company budget; return Retry-After seconds when denied."""
        ...


def _credentials(request: Request) -> Credential:
    bearer = request.headers.getlist("authorization")
    keys = request.headers.getlist("x-api-key")
    if bearer and keys:
        raise ReviewError("AMBIGUOUS_AUTHENTICATION")
    if len(bearer) > 1 or len(keys) > 1:
        raise ReviewError("UNAUTHORIZED")
    if bearer:
        prefix, separator, token = bearer[0].partition(" ")
        clean = token.strip()
        if prefix.lower() != "bearer" or not separator or not clean or " " in clean:
            raise ReviewError("UNAUTHORIZED")
        return Credential("bearer", clean)
    if keys and keys[0].strip():
        return Credential("api_key", keys[0].strip())
    raise ReviewError("UNAUTHORIZED")


def _meta(request: Request) -> Meta:
    return Meta(timestamp=datetime.now(timezone.utc),
                request_id=request.state.review_request_id)


def _unique_query(request: Request) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in request.query_params.multi_items():
        if key in result:
            raise invalid("query", "Repeated query fields are not allowed.")
        result[key] = value
    return result


def _path(value: str) -> UUID:
    try:
        return UUID(value)
    except (ValueError, AttributeError) as exc:
        raise invalid("document_id", "Expected a UUID.") from exc


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


async def _json(request: Request) -> object:
    length = request.headers.get("content-length")
    if length is not None:
        try:
            if int(length) > MAX_JSON_BODY_BYTES:
                raise invalid("body", "Review request body is too large.")
        except ValueError as exc:
            raise invalid("content-length", "Invalid Content-Length.") from exc
    body = await request.body()
    if not body or len(body) > MAX_JSON_BODY_BYTES:
        raise invalid("body", "Missing or oversized JSON body.")
    try:
        return json.loads(body.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise invalid("body", "Invalid JSON body.") from exc


class EnvelopeRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def wrapped(request: Request) -> Response:
            request.state.review_request_id = f"req_{uuid4().hex}"
            try:
                return await handler(request)
            except RequestValidationError:
                error = invalid("request", "Invalid request fields.")
            except ReviewError as exc:
                error = exc
            except Exception:
                logger.error("review_internal_error request_id=%s",
                             request.state.review_request_id)
                error = ReviewError("INTERNAL_ERROR")
            if error.status in (401, 403):
                logger.warning(
                    "review_access_denied status=%s source_ip=%s request_id=%s",
                    error.status,
                    request.client.host if request.client else "unknown",
                    request.state.review_request_id,
                )
            headers = {"Cache-Control": "no-store"}
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


def create_router(query_service: ReviewQueryService,
                  validation_service: ReviewValidationService,
                  command_service: ReviewCommandService,
                  auth: AuthResolver, limiter: RateLimiter) -> APIRouter:
    """Create review routes only when the host supplies every dependency.

    The generic detail route replaces/extends the existing ingestion detail route
    at composition time. A host must not register both handlers for the same path.
    """
    if any(value is None for value in (
        query_service, validation_service, command_service, auth, limiter,
    )):
        raise ValueError("Review services, shared auth, and limiter are mandatory")
    router = APIRouter(prefix="/api/v1/documents", tags=["document-review"],
                       route_class=EnvelopeRoute)

    async def caller_for(request: Request) -> Caller:
        caller = await auth.resolve(_credentials(request))
        retry_after = await limiter.check(caller)
        if retry_after is not None:
            raise ReviewError("RATE_LIMIT_EXCEEDED", retry_after=retry_after)
        return caller

    def no_query(request: Request) -> None:
        if request.query_params:
            raise invalid("query", "This route does not accept query fields.")

    @router.post("/{document_id}/review-validations",
                 response_model=Success[PreviewData])
    async def preview(request: Request, document_id: str) -> Success[PreviewData]:
        caller = await caller_for(request)
        no_query(request)
        try:
            payload = ReviewValidationRequest.model_validate(await _json(request))
        except ValidationError as exc:
            raise invalid("body", "Invalid review candidate.") from exc
        data = await validation_service.preview(caller, _path(document_id), payload)
        return Success(data=data, message="Review validation completed.",
                       meta=_meta(request))

    @router.put("/{document_id}/review", response_model=Success[MutationData])
    async def mutate(request: Request, document_id: str) -> Success[MutationData]:
        caller = await caller_for(request)
        no_query(request)
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
            payload = REVIEW_ACTION_ADAPTER.validate_python(await _json(request))
        except ValidationError as exc:
            raise invalid("body", "Invalid review action.") from exc
        outcome = await command_service.execute(
            caller, _path(document_id), payload,
            request.state.review_request_id, key,
        )
        return Success(data=outcome.data, message="Review action completed.",
                       meta=_meta(request))

    @router.get("/{document_id}/audit-logs", response_model=AuditLogResponse)
    async def audit(request: Request, document_id: str) -> AuditLogResponse:
        caller = await caller_for(request)
        try:
            query = AuditQuery.model_validate(_unique_query(request))
        except ValidationError as exc:
            raise invalid("query", "Invalid audit query fields.") from exc
        page = await query_service.list_audit_logs(caller, _path(document_id), query)
        return AuditLogResponse(data=page.rows, pagination=page.pagination,
                                message="Review audit history retrieved.",
                                meta=_meta(request))

    @router.get("/{document_id}", response_model=Success[ReviewDetail],
                responses=DETAIL_ERROR_RESPONSES,
                openapi_extra={"security": [{"BearerAuth": []}]})
    async def detail(request: Request, response: Response,
                     document_id: str) -> Success[ReviewDetail]:
        caller = await caller_for(request)
        no_query(request)
        data = await query_service.get_review_detail(caller, _path(document_id))
        response.headers["Cache-Control"] = "no-store"
        return Success(data=data, message="Document review retrieved.",
                       meta=_meta(request))

    return router
