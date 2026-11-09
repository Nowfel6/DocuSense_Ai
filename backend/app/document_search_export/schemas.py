"""Strict wire and domain models for document search and governed export.

No ORM or provider implementation is imported. Decimal inputs are fixed-point
strings on the wire and remain Decimal internally.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from typing import Annotated, Generic, Literal, TypeAlias, TypeVar
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StrictInt,
    model_validator,
)

Role = Literal["admin", "operator", "viewer"]
AuthKind = Literal["bearer", "api_key"]
SearchStatus = Literal["pending_review", "approved", "rejected"]
DocumentType = Literal["commercial_invoice", "purchase_order", "packing_list"]
SortBy = Literal["relevance", "date_issued", "grand_total", "created_at"]
SortOrder = Literal["asc", "desc"]
ExportFormat = Literal["csv", "xlsx", "json"]
ExportMode = Literal["synchronous", "asynchronous"]
ExportStatus = Literal["queued", "processing", "completed", "failed", "expired"]
ExportStage = Literal["accepted", "generating", "packaging", "storing", "completed"]
ArtifactContentType = Literal[
    "text/csv; charset=utf-8",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/json",
    "application/zip",
]

_DECIMAL_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_VISIBLE_ASCII_RE = re.compile(r"^[!-~]+$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_CONTROL_OR_BIDI = re.compile(r"[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]")


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _normalized_text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected text")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise ValueError("Blank text is not allowed")
    if _CONTROL_OR_BIDI.search(normalized):
        raise ValueError("Control characters are not allowed")
    return normalized


def _query_text(value: object) -> str:
    return _normalized_text(value)


def _supplier_text(value: object) -> str:
    return _normalized_text(value)


def _currency(value: object) -> str:
    if not isinstance(value, str) or not _CURRENCY_RE.fullmatch(value):
        raise ValueError("Expected a three-letter uppercase currency")
    return value


def _iso_date(value: object) -> date:
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Expected a real YYYY-MM-DD date") from exc
    if type(value) is date:
        return value
    raise ValueError("Expected YYYY-MM-DD")


def _money(value: object) -> Decimal:
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, str) and _DECIMAL_RE.fullmatch(value):
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("Expected a fixed-point decimal string") from exc
    else:
        raise ValueError("Expected a nonnegative fixed-point decimal string")
    if not result.is_finite() or result < 0 or result > Decimal("999999999999.99"):
        raise ValueError("Decimal exceeds allowed range")
    if max(0, -result.as_tuple().exponent) > 2:
        raise ValueError("Money accepts at most two decimal places")
    return result


def _idempotency_key(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ValueError("Expected 1..128 visible ASCII characters")
    if value != value.strip() or not _VISIBLE_ASCII_RE.fullmatch(value):
        raise ValueError("Expected trimmed visible ASCII characters")
    return value


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_utc)]
QueryText = Annotated[str, BeforeValidator(_query_text), Field(min_length=3, max_length=500)]
SupplierText = Annotated[str, BeforeValidator(_supplier_text), Field(min_length=1, max_length=255)]
Currency = Annotated[str, BeforeValidator(_currency)]
IsoDate = Annotated[date, BeforeValidator(_iso_date)]
Money = Annotated[
    Decimal,
    BeforeValidator(_money),
    PlainSerializer(lambda value: format(value, ".2f"), when_used="json"),
]
IdempotencyKey = Annotated[str, BeforeValidator(_idempotency_key)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Caller(Model):
    user_id: UUID
    company_id: UUID
    role: Role
    auth_kind: AuthKind = "bearer"
    is_active: bool = True


class SearchCriteria(Model):
    query: QueryText | None = None
    document_statuses: tuple[SearchStatus, ...] | None = None
    document_type: DocumentType | None = None
    supplier: SupplierText | None = None
    currency: Currency | None = None
    invoice_date_from: IsoDate | None = None
    invoice_date_to: IsoDate | None = None
    uploaded_from: UtcDatetime | None = None
    uploaded_to: UtcDatetime | None = None
    min_total: Money | None = None
    max_total: Money | None = None
    sort_by: SortBy | None = None
    order: SortOrder = "desc"

    @model_validator(mode="after")
    def validate_criteria(self) -> "SearchCriteria":
        filters = (
            self.document_statuses,
            self.document_type,
            self.supplier,
            self.currency,
            self.invoice_date_from,
            self.invoice_date_to,
            self.uploaded_from,
            self.uploaded_to,
            self.min_total,
            self.max_total,
        )
        if self.query is None and all(value is None for value in filters):
            raise ValueError("At least one query or structured filter is required")
        if self.document_statuses is not None:
            if not 1 <= len(self.document_statuses) <= 3:
                raise ValueError("document_statuses requires 1..3 values")
            if len(set(self.document_statuses)) != len(self.document_statuses):
                raise ValueError("document_statuses must be unique")
        if self.invoice_date_from and self.invoice_date_to:
            if self.invoice_date_from > self.invoice_date_to:
                raise ValueError("invoice_date_from must not exceed invoice_date_to")
        if self.uploaded_from and self.uploaded_to:
            if self.uploaded_from > self.uploaded_to:
                raise ValueError("uploaded_from must not exceed uploaded_to")
        if self.min_total is not None and self.max_total is not None:
            if self.min_total > self.max_total:
                raise ValueError("min_total must not exceed max_total")
        if self.sort_by == "relevance" and self.query is None:
            raise ValueError("relevance sorting requires query")
        if self.sort_by is None:
            object.__setattr__(self, "sort_by", "relevance" if self.query else "created_at")
        return self


class DocumentSearchRequest(SearchCriteria):
    page: Annotated[StrictInt, Field(ge=1)] = 1
    page_size: Annotated[StrictInt, Field(ge=1, le=100)] = 20


class CreateExportRequest(Model):
    format: ExportFormat
    document_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=50_000)] | None = None
    criteria: SearchCriteria | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> "CreateExportRequest":
        if (self.document_ids is None) == (self.criteria is None):
            raise ValueError("Exactly one export selection is required")
        if self.document_ids is not None and len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("document_ids must be unique")
        return self


class DirectExportRequest(Model):
    format: ExportFormat
    document_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=500)] | None = None
    criteria: SearchCriteria | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> "DirectExportRequest":
        if (self.document_ids is None) == (self.criteria is None):
            raise ValueError("Exactly one direct export selection is required")
        if self.document_ids is not None and len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("document_ids must be unique")
        if self.criteria is not None and self.criteria.query is not None:
            raise ValueError("Direct export does not accept semantic query")
        return self


class ErrorDetail(Model):
    field: Annotated[str, Field(min_length=1, max_length=100)]
    issue: Annotated[str, Field(min_length=1, max_length=300)]


class Meta(Model):
    timestamp: UtcDatetime
    request_id: Annotated[str, Field(min_length=1, max_length=128)]


class Pagination(Model):
    page: Annotated[int, Field(ge=1)]
    page_size: Annotated[int, Field(ge=1, le=100)]
    total_records: Annotated[int, Field(ge=0)]
    total_pages: Annotated[int, Field(ge=0)]
    has_next: bool
    has_prev: bool


class DocumentSearchResult(Model):
    document_id: UUID
    file_name: Annotated[str, Field(min_length=1, max_length=255)]
    document_type: DocumentType
    status: SearchStatus
    created_at: UtcDatetime
    invoice_id: UUID
    invoice_number: Annotated[str, Field(max_length=100)] | None
    supplier_name: Annotated[str, Field(max_length=255)] | None
    date_issued: date | None
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] | None
    grand_total: Money | None
    is_math_valid: bool
    review_revision: Annotated[int, Field(ge=0)]
    relevance_score: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)] | None
    matching_excerpt: Annotated[str, Field(max_length=500)] | None
    matching_chunk_id: UUID | None
    matching_page_start: Annotated[int, Field(ge=1)] | None
    matching_page_end: Annotated[int, Field(ge=1)] | None
    export_eligible: bool
    document_url: Annotated[str, Field(pattern=r"^/documents/")]
    review_url: Annotated[str, Field(pattern=r"^/documents/")] | None

    @model_validator(mode="after")
    def validate_match_shape(self) -> "DocumentSearchResult":
        if (self.matching_page_start is None) != (self.matching_page_end is None):
            raise ValueError("Matching page range must be complete or null")
        if self.matching_page_start is not None and self.matching_page_end is not None:
            if self.matching_page_start > self.matching_page_end:
                raise ValueError("matching page range is reversed")
        return self


class ExportResource(Model):
    export_id: UUID
    format: ExportFormat
    mode: ExportMode
    status: ExportStatus
    progress_percentage: Annotated[int, Field(ge=0, le=100)]
    current_stage: ExportStage
    selected_document_count: Annotated[int, Field(ge=1, le=50_000)]
    exported_document_count: Annotated[int, Field(ge=0, le=50_000)]
    row_count: Annotated[int, Field(ge=0, le=1_000_000)]
    created_at: UtcDatetime
    started_at: UtcDatetime | None
    completed_at: UtcDatetime | None
    artifact_expires_at: UtcDatetime | None
    status_url: Annotated[str, Field(pattern=r"^/api/v1/exports/")]
    download_url: Annotated[str, Field(pattern=r"^/api/v1/exports/")] | None


class ExportStatusResource(ExportResource):
    error_code: Annotated[str, Field(max_length=100)] | None = None
    error_message: Annotated[str, Field(max_length=1000)] | None = None


DataT = TypeVar("DataT")


class Success(Model, Generic[DataT]):
    success: Literal[True] = True
    data: DataT
    message: Annotated[str, Field(min_length=1, max_length=300)]
    meta: Meta


class SearchSuccess(Success[tuple[DocumentSearchResult, ...]]):
    pagination: Pagination


class ErrorBody(Model):
    code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]+$", max_length=100)]
    message: Annotated[str, Field(min_length=1, max_length=300)]
    details: tuple[ErrorDetail, ...] = ()


class ErrorEnvelope(Model):
    success: Literal[False] = False
    error: ErrorBody
    meta: Meta


class DownloadGrant(Model):
    kind: Literal["stream", "redirect"]
    file_name: Annotated[str, Field(
        min_length=1, max_length=255, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"
    )]
    content_type: ArtifactContentType
    content_length: Annotated[int, Field(gt=0)]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    body: bytes | None = Field(default=None, repr=False)
    url: Annotated[str, Field(pattern=r"^https://")] | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def validate_shape(self) -> "DownloadGrant":
        if self.file_name in {".", ".."}:
            raise ValueError("Unsafe artifact file name")
        if self.kind == "stream" and (self.body is None or self.url is not None):
            raise ValueError("Stream grant requires body only")
        if self.kind == "redirect" and (self.url is None or self.body is not None):
            raise ValueError("Redirect grant requires URL only")
        if self.body is not None and len(self.body) != self.content_length:
            raise ValueError("Stream length does not match metadata")
        return self


JsonScalar: TypeAlias = str | int | bool | None
JsonValue: TypeAlias = JsonScalar | tuple["JsonValue", ...] | dict[str, "JsonValue"]


class IdempotencyHeader(Model):
    value: IdempotencyKey


__all__ = [name for name in globals() if not name.startswith("_")]


