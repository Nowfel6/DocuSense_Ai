"""Feature 06 FastAPI routes with injected auth, limits, and services."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import re
from typing import Literal, Protocol
from uuid import uuid4

from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.responses import JSONResponse

from .errors import DashboardActivityError, invalid
from .schemas import (
    ActivityQuery,
    ActivitySuccess,
    Caller,
    DashboardData,
    DashboardQuery,
    ErrorBody,
    ErrorEnvelope,
    Meta,
    Success,
)
from .service import ActivityService, AnalyticsService

logger = logging.getLogger("dashboard_activity")
PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
}
_POSITIVE_INTEGER = re.compile(r"^[1-9][0-9]*$")


@dataclass(frozen=True)
class Credential:
    kind: Literal["bearer", "api_key"]
    secret: str = field(repr=False)


class AuthResolver(Protocol):
    async def resolve(self, credential: Credential) -> Caller:
        """Validate one credential and return persisted active human context."""
        ...


class RateLimiter(Protocol):
    async def check(self, caller: Caller, operation: str) -> int | None:
        """Apply independent atomic user/company budgets."""
        ...


def _credentials(request: Request) -> Credential:
    bearer = request.headers.getlist("authorization")
    keys = request.headers.getlist("x-api-key")
    if bearer and keys:
        raise DashboardActivityError("AMBIGUOUS_AUTHENTICATION")
    if len(bearer) > 1 or len(keys) > 1:
        raise DashboardActivityError("UNAUTHORIZED")
    if bearer:
        prefix, separator, token = bearer[0].partition(" ")
        clean = token.strip()
        if prefix.lower() != "bearer" or not separator or not clean or " " in clean:
            raise DashboardActivityError("UNAUTHORIZED")
        return Credential("bearer", clean)
    if keys and keys[0].strip():
        return Credential("api_key", keys[0].strip())
    raise DashboardActivityError("UNAUTHORIZED")


def _meta(request: Request) -> Meta:
    return Meta(
        timestamp=datetime.now(timezone.utc),
        request_id=request.state.dashboard_request_id,
    )


def _reject_body(request: Request) -> None:
    lengths = request.headers.getlist("content-length")
    if len(lengths) > 1:
        raise invalid("content-length", "Repeated Content-Length is not allowed.")
    if request.headers.get("transfer-encoding"):
        raise invalid("body", "A request body is not allowed.")
    if lengths:
        try:
            if int(lengths[0]) != 0:
                raise invalid("body", "A request body is not allowed.")
        except ValueError as exc:
            raise invalid("content-length", "Invalid Content-Length.") from exc


def _strict_integer(field_name: str, value: str) -> int:
    if not _POSITIVE_INTEGER.fullmatch(value):
        raise invalid(field_name, "Expected a positive base-10 integer.")
    return int(value)


def _dashboard_query(request: Request) -> DashboardQuery:
    allowed = {"from", "to", "bucket"}
    payload: dict[str, object] = {}
    for key, value in request.query_params.multi_items():
        if key not in allowed:
            raise invalid("query", "Unknown dashboard query field.")
        if key in payload:
            raise invalid(key, "Repeated scalar query field is not allowed.")
        payload[key] = value
    try:
        return DashboardQuery.model_validate(payload)
    except ValidationError as exc:
        raise invalid("query", "Invalid dashboard query.") from exc


def _activity_query(request: Request) -> ActivityQuery:
    scalar_fields = {"page", "page_size", "from", "to", "snapshot_at"}
    allowed = scalar_fields | {"event_type"}
    payload: dict[str, object] = {}
    event_types: list[str] = []
    for key, value in request.query_params.multi_items():
        if key not in allowed:
            raise invalid("query", "Unknown activity query field.")
        if key == "event_type":
            event_types.append(value)
        elif key in payload:
            raise invalid(key, "Repeated scalar query field is not allowed.")
        elif key in {"page", "page_size"}:
            payload[key] = _strict_integer(key, value)
        else:
            payload[key] = value
    payload["event_type"] = event_types
    try:
        return ActivityQuery.model_validate(payload)
    except ValidationError as exc:
        raise invalid("query", "Invalid activity query.") from exc


class EnvelopeRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def wrapped(request: Request) -> Response:
            request.state.dashboard_request_id = f"req_{uuid4().hex}"
            try:
                response = await handler(request)
                for key, value in PRIVATE_HEADERS.items():
                    response.headers.setdefault(key, value)
                response.headers.setdefault("X-Request-Id", request.state.dashboard_request_id)
                return response
            except RequestValidationError:
                error = invalid("request", "Invalid request fields.")
            except DashboardActivityError as exc:
                error = exc
            except Exception:
                logger.error(
                    "dashboard_internal_error request_id=%s operation=%s",
                    request.state.dashboard_request_id,
                    "activity_events" if request.url.path.endswith("activity-events") else "analytics_dashboard",
                )
                error = DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
            if error.status in (401, 403):
                logger.warning(
                    "dashboard_access_denied status=%s source_ip=%s request_id=%s",
                    error.status,
                    request.client.host if request.client else "unknown",
                    request.state.dashboard_request_id,
                )
            headers = dict(PRIVATE_HEADERS)
            headers["X-Request-Id"] = request.state.dashboard_request_id
            if error.retry_after is not None:
                headers["Retry-After"] = str(max(1, error.retry_after))
            envelope = ErrorEnvelope(
                error=ErrorBody(code=error.code, message=error.message, details=error.details),
                meta=_meta(request),
            )
            return JSONResponse(
                envelope.model_dump(mode="json", by_alias=True),
                status_code=error.status,
                headers=headers,
            )

        return wrapped


def create_router(analytics: AnalyticsService, activity: ActivityService,
                  auth: AuthResolver, limiter: RateLimiter) -> APIRouter:
    """Create Feature 06 routes only when every shared dependency is supplied."""
    if any(value is None for value in (analytics, activity, auth, limiter)):
        raise ValueError("Analytics/activity services, auth, and limiter are mandatory")
    router = APIRouter(
        prefix="/api/v1", tags=["dashboard-activity"], route_class=EnvelopeRoute,
    )

    async def caller_for(request: Request, operation: str) -> Caller:
        caller = await auth.resolve(_credentials(request))
        retry_after = await limiter.check(caller, operation)
        if retry_after is not None:
            raise DashboardActivityError("RATE_LIMIT_EXCEEDED", retry_after=retry_after)
        return caller

    @router.get("/analytics/dashboard", response_model=Success[DashboardData])
    async def dashboard(request: Request) -> Success[DashboardData]:
        _reject_body(request)
        caller = await caller_for(request, "analytics_dashboard")
        data = await analytics.get_dashboard(caller, _dashboard_query(request))
        return Success(data=data, message="Dashboard analytics loaded.", meta=_meta(request))

    @router.get("/activity-events", response_model=ActivitySuccess)
    async def activity_events(request: Request) -> ActivitySuccess:
        _reject_body(request)
        caller = await caller_for(request, "activity_events")
        data, pagination = await activity.list_events(caller, _activity_query(request))
        return ActivitySuccess(
            data=data, pagination=pagination,
            message="Recent activity loaded.", meta=_meta(request),
        )

    return router


__all__ = ["AuthResolver", "Credential", "RateLimiter", "create_router"]
