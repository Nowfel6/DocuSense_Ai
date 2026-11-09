"""Strict wire/domain models for human review and immutable audit.

No ORM model is imported here. Decimal inputs are fixed-point strings on the
wire and remain Decimal values internally.
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
    TypeAdapter,
    model_validator,
)

Action = Literal["save", "approve", "reject", "reopen"]
AuditAction = Literal["field_edited", "approved", "rejected", "reopened"]
DocumentStatus = Literal["pending_review", "approved", "rejected"]
DetailDocumentStatus = Literal[
    "queued", "partitioning", "chunking", "vectorizing", "extracting",
    "pending_review", "approved", "rejected", "failed",
]
DetailDocumentType = Literal["commercial_invoice", "purchase_order", "packing_list"]
Origin = Literal["extracted", "reviewer_added"]
ChangeKind = Literal["set", "add", "remove", "reorder"]
RuleStatus = Literal["passed", "failed", "missing", "not_applicable"]
Role = Literal["admin", "operator", "viewer"]
PermittedAction = Literal["save", "approve", "reject", "reopen"]
MimeType = Literal["application/pdf", "image/png", "image/jpeg"]

_DECIMAL_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_QUERY_INT_RE = re.compile(r"^[0-9]+$")
_VISIBLE_ASCII_RE = re.compile(r"^[!-~]+$")
_BIDI_CONTROLS = {
    "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
    "\u2066", "\u2067", "\u2068", "\u2069",
}


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Expected text or null")
    result = unicodedata.normalize("NFC", value).strip()
    if not result or result.casefold() in {"n/a", "none", "null"}:
        raise ValueError("Blank or sentinel text is not allowed")
    if any(ord(char) < 32 or ord(char) == 127 or char in _BIDI_CONTROLS for char in result):
        raise ValueError("Control characters are not allowed")
    return result


def _required_text(value: object) -> str:
    result = _text(value)
    if result is None:
        raise ValueError("Expected nonempty text")
    return result


def _decimal(value: object, *, digits: int, places: int) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, str) and _DECIMAL_RE.fullmatch(value):
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("Expected a fixed-point decimal string") from exc
    else:
        raise ValueError("Expected a fixed-point decimal string")
    if not result.is_finite() or result < 0:
        raise ValueError("Expected a finite nonnegative decimal")
    exponent = result.as_tuple().exponent
    scale = max(0, -exponent)
    integer_digits = (len(result.as_tuple().digits) + exponent if exponent >= 0
                      else max(1, len(result.as_tuple().digits) - scale))
    if scale > places or integer_digits > digits - places:
        raise ValueError("Decimal exceeds allowed precision")
    return result


def _money(value: object) -> Decimal | None:
    return _decimal(value, digits=14, places=2)


def _quantity(value: object) -> Decimal | None:
    return _decimal(value, digits=18, places=4)


def _unit_price(value: object) -> Decimal | None:
    return _decimal(value, digits=14, places=4)


def _date(value: object) -> date | None:
    if value is None or type(value) is date:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Expected a real YYYY-MM-DD date") from exc
    raise ValueError("Expected YYYY-MM-DD or null")


def _query_int(value: object) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str) and _QUERY_INT_RE.fullmatch(value):
        return int(value)
    raise ValueError("Expected a base-10 integer")


def _idempotency_key(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ValueError("Expected 1..128 visible ASCII characters")
    if value != value.strip() or not _VISIBLE_ASCII_RE.fullmatch(value):
        raise ValueError("Expected trimmed visible ASCII characters")
    return value


def _https(value: str) -> str:
    if not value.startswith("https://"):
        raise ValueError("Source URL must use HTTPS")
    return value


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_utc)]
Money = Annotated[
    Decimal | None,
    BeforeValidator(_money),
    PlainSerializer(lambda value: None if value is None else format(value, ".2f"), when_used="json"),
]
Quantity = Annotated[
    Decimal | None,
    BeforeValidator(_quantity),
    PlainSerializer(lambda value: None if value is None else format(value, ".4f"), when_used="json"),
]
UnitPrice = Annotated[
    Decimal | None,
    BeforeValidator(_unit_price),
    PlainSerializer(lambda value: None if value is None else format(value, ".4f"), when_used="json"),
]
SixPlaceDecimal = Annotated[
    Decimal | None,
    PlainSerializer(lambda value: None if value is None else format(value, ".6f"), when_used="json"),
]
Confidence = Annotated[
    Decimal | None,
    Field(ge=0, le=100, allow_inf_nan=False),
    PlainSerializer(
        lambda value: None if value is None else float(value),
        return_type=float | None,
        when_used="json",
    ),
]
IdempotencyKey = Annotated[str, BeforeValidator(_idempotency_key)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InvoiceCandidate(Model):
    invoice_number: Annotated[str, BeforeValidator(_required_text), Field(max_length=100)] | None
    supplier_name: Annotated[str, BeforeValidator(_required_text), Field(max_length=255)] | None
    supplier_tax_id: Annotated[str, BeforeValidator(_required_text), Field(max_length=100)] | None
    buyer_name: Annotated[str, BeforeValidator(_required_text), Field(max_length=255)] | None
    date_issued: Annotated[date | None, BeforeValidator(_date)]
    due_date: Annotated[date | None, BeforeValidator(_date)]
    currency: Annotated[str, BeforeValidator(_required_text), Field(pattern=r"^[A-Z]{3}$")] | None
    subtotal: Money
    tax_amount: Money
    discount_amount: Money
    grand_total: Money


class LineItemCandidate(Model):
    line_item_id: UUID | None = None
    client_correlation_key: Annotated[
        str, BeforeValidator(_required_text), Field(max_length=128)
    ] | None = None
    description: Annotated[str, BeforeValidator(_required_text), Field(max_length=32768)] | None
    hs_code: Annotated[str, BeforeValidator(_required_text), Field(max_length=50)] | None
    quantity: Quantity
    unit_price: UnitPrice
    tax_amount: Money
    total_price: Money
    line_order: Annotated[int, Field(strict=True, ge=1, le=500)]

    @model_validator(mode="after")
    def one_identity(self) -> "LineItemCandidate":
        if (self.line_item_id is None) == (self.client_correlation_key is None):
            raise ValueError("Supply exactly one line identity")
        return self


class CandidatePayload(Model):
    invoice: InvoiceCandidate
    line_items: tuple[LineItemCandidate, ...] = Field(max_length=500)

    @model_validator(mode="after")
    def ordered_unique_lines(self) -> "CandidatePayload":
        expected = list(range(1, len(self.line_items) + 1))
        if [line.line_order for line in self.line_items] != expected:
            raise ValueError("line_order must match contiguous array order")
        ids = [line.line_item_id for line in self.line_items if line.line_item_id is not None]
        keys = [line.client_correlation_key for line in self.line_items
                if line.client_correlation_key is not None]
        if len(ids) != len(set(ids)) or len(keys) != len(set(keys)):
            raise ValueError("Line identities must be unique")
        return self


class ReviewValidationRequest(CandidatePayload):
    expected_review_revision: Annotated[
        int, Field(strict=True, ge=0, le=9_223_372_036_854_775_807)
    ]


class SaveReviewRequest(ReviewValidationRequest):
    action: Literal["save"]
    note: Annotated[str, BeforeValidator(_required_text), Field(max_length=1000)] | None = None


class ApproveReviewRequest(ReviewValidationRequest):
    action: Literal["approve"]
    note: Annotated[str, BeforeValidator(_required_text), Field(max_length=1000)] | None = None


class RejectReviewRequest(Model):
    action: Literal["reject"]
    expected_review_revision: Annotated[
        int, Field(strict=True, ge=0, le=9_223_372_036_854_775_807)
    ]
    reason: Annotated[str, BeforeValidator(_required_text), Field(max_length=1000)]


class ReopenReviewRequest(Model):
    action: Literal["reopen"]
    expected_review_revision: Annotated[
        int, Field(strict=True, ge=0, le=9_223_372_036_854_775_807)
    ]
    reason: Annotated[str, BeforeValidator(_required_text), Field(max_length=1000)]


ReviewActionRequest: TypeAlias = Annotated[
    SaveReviewRequest | ApproveReviewRequest | RejectReviewRequest | ReopenReviewRequest,
    Field(discriminator="action"),
]
REVIEW_ACTION_ADAPTER = TypeAdapter(ReviewActionRequest)


class AuditQuery(Model):
    page: Annotated[int, BeforeValidator(_query_int), Field(ge=1)] = 1
    page_size: Annotated[int, BeforeValidator(_query_int), Field(ge=1, le=100)] = 20
    action: AuditAction | None = None


class Caller(Model):
    """Trusted shared-auth result; request data must never construct this model."""
    company_id: UUID
    user_id: UUID | None = None
    role: Role | None = None
    api_key_id: UUID | None = None

    @model_validator(mode="after")
    def one_identity(self) -> "Caller":
        human = self.user_id is not None and self.role is not None and self.api_key_id is None
        key = self.api_key_id is not None and self.user_id is None and self.role is None
        if not (human or key):
            raise ValueError("Exactly one trusted caller identity is required")
        return self


class Meta(Model):
    timestamp: UtcDatetime
    request_id: Annotated[str, Field(min_length=1, max_length=128)]


class ErrorDetail(Model):
    field: Annotated[str, Field(min_length=1, max_length=255)]
    issue: Annotated[str, Field(min_length=1, max_length=255)]


class ErrorBody(Model):
    code: Annotated[str, Field(min_length=1, max_length=100)]
    message: Annotated[str, Field(min_length=1, max_length=255)]
    details: tuple[ErrorDetail, ...] = ()


class ErrorEnvelope(Model):
    success: Literal[False] = False
    error: ErrorBody
    meta: Meta


DataT = TypeVar("DataT")


class Success(Model, Generic[DataT]):
    success: Literal[True] = True
    data: DataT
    message: str
    meta: Meta


class ResolvedLineCandidate(Model):
    line_item_id: UUID
    origin: Origin
    client_correlation_key: str | None = None
    description: str | None
    hs_code: str | None
    quantity: Quantity
    unit_price: UnitPrice
    tax_amount: Money
    total_price: Money
    line_order: Annotated[int, Field(strict=True, ge=1, le=500)]


class ResolvedCandidate(Model):
    invoice: InvoiceCandidate
    line_items: tuple[ResolvedLineCandidate, ...] = Field(max_length=500)


JsonScalar: TypeAlias = str | int | bool | None


class RuleResult(Model):
    rule_id: Annotated[str, Field(min_length=1, max_length=64)]
    scope_key: Annotated[str, Field(min_length=1, max_length=255)]
    status: RuleStatus
    observed_value: JsonScalar = None
    expected_value: JsonScalar = None
    difference: SixPlaceDecimal = None
    epsilon: SixPlaceDecimal = None
    message_code: Annotated[str, Field(min_length=1, max_length=100)]
    blocks_approval: bool

    @model_validator(mode="after")
    def comparison_shape(self) -> "RuleResult":
        if self.status in ("missing", "not_applicable"):
            if self.difference is not None or self.epsilon is not None:
                raise ValueError("Missing/not-applicable rules have no comparison values")
        if self.rule_id.startswith("BR-03.") and self.status in ("passed", "failed"):
            if self.difference is None or self.epsilon != Decimal("0.050000"):
                raise ValueError("BR-03 comparisons require difference and epsilon")
            if (self.status == "passed") != (self.difference <= self.epsilon):
                raise ValueError("BR-03 status conflicts with inclusive epsilon")
        return self


class ValidationSummary(Model):
    passed: Annotated[int, Field(strict=True, ge=0)]
    failed: Annotated[int, Field(strict=True, ge=0)]
    missing: Annotated[int, Field(strict=True, ge=0)]
    not_applicable: Annotated[int, Field(strict=True, ge=0)]


class ValidationReport(Model):
    validation_version: Literal["human-review-v1"] = "human-review-v1"
    is_math_valid: bool
    approval_eligible: bool
    summary: ValidationSummary
    results: tuple[RuleResult, ...]
    warnings: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()


class ValidationBundle(Model):
    validation_version: Literal["human-review-v1"] = "human-review-v1"
    candidate_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    is_math_valid: bool
    approval_eligible: bool
    summary: ValidationSummary
    results: tuple[RuleResult, ...]
    warnings: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def derived_shape(self) -> "ValidationBundle":
        identities = [(row.rule_id, row.scope_key) for row in self.results]
        if not identities or len(identities) != len(set(identities)):
            raise ValueError("Validation rule identities must be nonempty and unique")
        counts = {
            status: sum(row.status == status for row in self.results)
            for status in ("passed", "failed", "missing", "not_applicable")
        }
        if self.summary.model_dump() != counts:
            raise ValueError("Validation summary does not match results")
        blockers = tuple(row.message_code for row in self.results
                         if row.blocks_approval and row.status in ("failed", "missing"))
        if self.blocking_reasons != blockers:
            raise ValueError("Blocking reasons do not match results")
        if self.approval_eligible != (not blockers and self.is_math_valid):
            raise ValueError("Approval eligibility is inconsistent")
        return self

    def public(self) -> ValidationReport:
        return ValidationReport(
            is_math_valid=self.is_math_valid,
            approval_eligible=self.approval_eligible,
            summary=self.summary,
            results=self.results,
            warnings=self.warnings,
            blocking_reasons=self.blocking_reasons,
        )


class ReviewLineItem(Model):
    line_item_id: UUID
    origin: Origin
    line_order: Annotated[int, Field(strict=True, ge=1, le=500)]
    description: str | None
    hs_code: str | None
    quantity: Quantity
    unit_price: UnitPrice
    tax_amount: Money
    total_price: Money


class ReviewInvoice(Model):
    invoice_id: UUID
    invoice_number: str | None
    supplier_name: str | None
    supplier_tax_id: str | None
    buyer_name: str | None
    date_issued: date | None
    due_date: date | None
    currency: str | None
    subtotal: Money
    tax_amount: Money
    discount_amount: Money
    grand_total: Money
    is_math_valid: bool
    line_items: tuple[ReviewLineItem, ...]

    @model_validator(mode="after")
    def ordered_lines(self) -> "ReviewInvoice":
        ids = [line.line_item_id for line in self.line_items]
        if len(ids) != len(set(ids)):
            raise ValueError("Review line IDs must be unique")
        if [line.line_order for line in self.line_items] != list(range(1, len(ids) + 1)):
            raise ValueError("Review lines must have contiguous order")
        return self


class PreviewLineItem(Model):
    line_item_id: UUID | None
    client_correlation_key: str | None
    origin: Origin
    line_order: int
    description: str | None
    hs_code: str | None
    quantity: Quantity
    unit_price: UnitPrice
    tax_amount: Money
    total_price: Money
    calculated_total_price: Money


class PreviewData(Model):
    review_revision: Annotated[int, Field(strict=True, ge=0)]
    invoice: InvoiceCandidate
    line_items: tuple[PreviewLineItem, ...]
    calculated_subtotal: Money
    calculated_grand_total: Money
    validation: ValidationReport


class SourceView(Model):
    url: Annotated[str, AfterValidator(_https)]
    expires_at: UtcDatetime
    mime_type: MimeType
    page_count: Annotated[int | None, Field(ge=1)] = None


class EvidenceSummary(Model):
    field_path: Annotated[str, Field(min_length=1, max_length=255)]
    source_page: Annotated[int | None, Field(ge=1)] = None
    evidence_excerpt: Annotated[str | None, Field(max_length=1000)] = None
    confidence_score: Annotated[
        Decimal,
        Field(ge=0, le=100, allow_inf_nan=False),
        PlainSerializer(float, return_type=float, when_used="json"),
    ]
    validation_state: Literal["valid", "invalid", "missing", "ambiguous", "unsupported"]


class ReviewDetail(Model):
    document_id: UUID
    file_name: Annotated[str, Field(min_length=1, max_length=255)]
    file_size_bytes: Annotated[int, Field(strict=True, ge=1, le=10_485_760)]
    mime_type: MimeType
    doc_type: DetailDocumentType
    status: DetailDocumentStatus
    overall_confidence: Confidence
    created_at: UtcDatetime
    updated_at: UtcDatetime
    job_id: UUID
    uploaded_by: UUID | None
    review_revision: Annotated[int, Field(strict=True, ge=0)] | None
    permitted_actions: tuple[PermittedAction, ...]
    invoice: ReviewInvoice | None
    extraction_validation: ValidationSummary | None
    field_evidence: tuple[EvidenceSummary, ...]
    latest_review_validation: ValidationReport | None
    source_view: SourceView


class MutationData(Model):
    document_id: UUID
    status: DocumentStatus
    review_revision: Annotated[int, Field(strict=True, ge=1)]
    invoice: ReviewInvoice
    latest_review_validation: ValidationReport | None
    audit_event_id: UUID
    permitted_actions: tuple[PermittedAction, ...]


class AuditChange(Model):
    field_path: Annotated[str, Field(min_length=1, max_length=255)]
    change_kind: ChangeKind
    old_value: JsonScalar | dict[str, JsonScalar] | tuple[JsonScalar, ...] = None
    new_value: JsonScalar | dict[str, JsonScalar] | tuple[JsonScalar, ...] = None

    @model_validator(mode="after")
    def value_shape(self) -> "AuditChange":
        if self.change_kind == "set" and self.old_value == self.new_value:
            raise ValueError("Set values must differ")
        if self.change_kind == "add" and (self.old_value is not None or self.new_value is None):
            raise ValueError("Add requires null old and non-null new")
        if self.change_kind == "remove" and (self.old_value is None or self.new_value is not None):
            raise ValueError("Remove requires non-null old and null new")
        if self.change_kind == "reorder" and (
            not isinstance(self.old_value, tuple) or not isinstance(self.new_value, tuple)
            or self.old_value == self.new_value or set(self.old_value) != set(self.new_value)
        ):
            raise ValueError("Reorder requires different arrays with equal members")
        return self


class AuditEvent(Model):
    audit_event_id: UUID
    actor_user_id: UUID
    actor_display_name: str | None
    action: AuditAction
    from_status: DocumentStatus
    to_status: DocumentStatus
    review_revision: Annotated[int, Field(strict=True, ge=1)]
    reason: str | None
    note: str | None
    request_id: Annotated[str, Field(min_length=1, max_length=128)]
    created_at: UtcDatetime
    changes: tuple[AuditChange, ...]

    @model_validator(mode="after")
    def action_shape(self) -> "AuditEvent":
        expected = {
            "field_edited": ("pending_review", "pending_review"),
            "approved": ("pending_review", "approved"),
            "rejected": ("pending_review", "rejected"),
            "reopened": ("approved", "pending_review"),
        }[self.action]
        if (self.from_status, self.to_status) != expected:
            raise ValueError("Audit transition conflicts with action")
        if self.action in ("rejected", "reopened"):
            if self.reason is None or self.note is not None or self.changes:
                raise ValueError("Decision/reopen audit shape is invalid")
        else:
            if self.reason is not None:
                raise ValueError("Save/approve reason must be null")
            if self.action == "field_edited" and not self.changes:
                raise ValueError("Save event requires changes")
        return self


class Pagination(Model):
    page: Annotated[int, Field(strict=True, ge=1)]
    page_size: Annotated[int, Field(strict=True, ge=1, le=100)]
    total_records: Annotated[int, Field(strict=True, ge=0)]
    total_pages: Annotated[int, Field(strict=True, ge=0)]
    has_next: bool
    has_prev: bool

    @classmethod
    def create(cls, query: AuditQuery, total: int) -> "Pagination":
        pages = (total + query.page_size - 1) // query.page_size
        return cls(page=query.page, page_size=query.page_size, total_records=total,
                   total_pages=pages, has_next=query.page < pages,
                   has_prev=query.page > 1 and total > 0)


class AuditPage(Model):
    rows: tuple[AuditEvent, ...]
    pagination: Pagination


class AuditLogResponse(Model):
    success: Literal[True] = True
    data: tuple[AuditEvent, ...]
    message: str
    meta: Meta
    pagination: Pagination


class IdempotencyHeader(Model):
    value: IdempotencyKey
