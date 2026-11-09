"""Strict Feature 06 wire and domain models.

All public times are explicit UTC instants. Rates remain Decimal internally and
serialize as fixed two-decimal strings. No ORM model is imported here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import re
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
Bucket = Literal["day", "week", "month"]
DocumentStatus = Literal[
    "queued", "partitioning", "chunking", "vectorizing", "extracting",
    "pending_review", "approved", "rejected", "failed",
]
ActivityEventType = Literal[
    "document_uploaded", "processing_completed", "processing_failed",
    "review_saved", "document_approved", "document_rejected",
    "document_reopened", "export_requested", "export_completed",
    "export_failed", "export_expired",
]
ActivitySummaryCode = Literal[
    "document.uploaded", "processing.completed", "processing.failed",
    "review.field_edited", "review.approved", "review.rejected",
    "review.reopened", "export.requested", "export.completed",
    "export.failed", "export.expired",
]
SubjectType = Literal["document", "export"]
SourceAvailability = Literal["available"]

EVENT_TYPES: tuple[ActivityEventType, ...] = (
    "document_uploaded", "processing_completed", "processing_failed",
    "review_saved", "document_approved", "document_rejected",
    "document_reopened", "export_requested", "export_completed",
    "export_failed", "export_expired",
)
DOCUMENT_STATUSES: tuple[DocumentStatus, ...] = (
    "queued", "partitioning", "chunking", "vectorizing", "extracting",
    "pending_review", "approved", "rejected", "failed",
)

_CONTROL_OR_BIDI = re.compile(r"[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]")
_RELATIVE_LINK = re.compile(r"^/(?!/)[^\\\x00-\x1f\x7f]{1,499}$")
_RATE = Decimal("0.01")


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _wire_datetime(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("A timezone-aware timestamp is required")
        return value
    if not isinstance(value, str):
        raise ValueError("An RFC 3339 timestamp is required")
    candidate = value.strip()
    if candidate != value or "T" not in candidate:
        raise ValueError("An explicit date-time instant is required")
    normalized = candidate[:-1] + "+00:00" if candidate.endswith(("Z", "z")) else candidate
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("An RFC 3339 timestamp is required") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("A timezone offset is required")
    return parsed


def _rate(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("A finite Decimal rate is required")
    result = value.quantize(_RATE)
    if result < 0 or result > 100:
        raise ValueError("Rate must be between zero and one hundred")
    return result


def _plain_text(value: str) -> str:
    if _CONTROL_OR_BIDI.search(value):
        raise ValueError("Control characters are not allowed")
    return value


def _relative_link(value: str) -> str:
    if not _RELATIVE_LINK.fullmatch(value) or "://" in value:
        raise ValueError("A safe application-relative link is required")
    return value


UtcDatetime = Annotated[
    AwareDatetime, BeforeValidator(_wire_datetime), AfterValidator(_utc),
]
Rate = Annotated[
    Decimal,
    AfterValidator(_rate),
    PlainSerializer(lambda value: format(value, ".2f"), when_used="json"),
]
PlainLabel = Annotated[str, AfterValidator(_plain_text), Field(min_length=1, max_length=255)]
ActorName = Annotated[str, AfterValidator(_plain_text), Field(min_length=1, max_length=100)]
RelativeLink = Annotated[str, BeforeValidator(_relative_link)]
NonNegativeInt = Annotated[StrictInt, Field(ge=0)]
Duration = Annotated[StrictInt, Field(ge=0)]


class Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, populate_by_name=True, validate_default=True,
    )


class Caller(Model):
    user_id: UUID
    company_id: UUID
    role: Role
    auth_kind: AuthKind = "bearer"
    is_active: bool = True


class DashboardQuery(Model):
    from_at: UtcDatetime | None = Field(default=None, alias="from")
    to_at: UtcDatetime | None = Field(default=None, alias="to")
    bucket: Bucket = "day"

    @model_validator(mode="after")
    def paired_range(self) -> "DashboardQuery":
        if (self.from_at is None) != (self.to_at is None):
            raise ValueError("from and to must be supplied together")
        if self.from_at is not None and self.to_at is not None and self.from_at >= self.to_at:
            raise ValueError("from must be earlier than to")
        return self


class ActivityQuery(Model):
    page: Annotated[StrictInt, Field(ge=1)] = 1
    page_size: Annotated[StrictInt, Field(ge=1, le=100)] = 20
    event_type: tuple[ActivityEventType, ...] = ()
    from_at: UtcDatetime | None = Field(default=None, alias="from")
    to_at: UtcDatetime | None = Field(default=None, alias="to")
    snapshot_at: UtcDatetime | None = None

    @model_validator(mode="after")
    def valid_page_and_range(self) -> "ActivityQuery":
        if len(set(self.event_type)) != len(self.event_type):
            raise ValueError("event_type values must be unique")
        if (self.from_at is None) != (self.to_at is None):
            raise ValueError("from and to must be supplied together")
        if self.from_at is not None and self.to_at is not None and self.from_at >= self.to_at:
            raise ValueError("from must be earlier than to")
        if self.page == 1 and self.snapshot_at is not None:
            raise ValueError("snapshot_at is forbidden on page 1")
        if self.page > 1 and self.snapshot_at is None:
            raise ValueError("snapshot_at is required after page 1")
        return self


class Meta(Model):
    timestamp: UtcDatetime
    request_id: Annotated[str, Field(min_length=1, max_length=128)]


class ErrorDetail(Model):
    field: Annotated[str, Field(min_length=1, max_length=100)]
    issue: Annotated[str, Field(min_length=1, max_length=300)]


class ErrorBody(Model):
    code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]+$", max_length=100)]
    message: Annotated[str, Field(min_length=1, max_length=300)]
    details: tuple[ErrorDetail, ...] = ()


class ErrorEnvelope(Model):
    success: Literal[False] = False
    error: ErrorBody
    meta: Meta


DataT = TypeVar("DataT")


class Success(Model, Generic[DataT]):
    success: Literal[True] = True
    data: DataT
    message: Annotated[str, Field(min_length=1, max_length=300)]
    meta: Meta


class Pagination(Model):
    page: Annotated[StrictInt, Field(ge=1)]
    page_size: Annotated[StrictInt, Field(ge=1, le=100)]
    total_records: NonNegativeInt
    total_pages: NonNegativeInt
    has_next: bool
    has_prev: bool


class DashboardPeriod(Model):
    from_at: UtcDatetime = Field(alias="from")
    to_at: UtcDatetime = Field(alias="to")
    bucket: Bucket
    snapshot_at: UtcDatetime


class SourceStatus(Model):
    auth: SourceAvailability = "available"
    ingestion: SourceAvailability = "available"
    processing: SourceAvailability = "available"
    review: SourceAvailability = "available"
    export: SourceAvailability = "available"


class CurrentDashboardMetrics(Model):
    total_documents: NonNegativeInt
    active_processing_documents: NonNegativeInt
    pending_review_documents: NonNegativeInt
    approved_documents: NonNegativeInt
    failed_documents: NonNegativeInt
    active_export_jobs: NonNegativeInt


class PeriodDashboardMetrics(Model):
    documents_uploaded: NonNegativeInt
    processing_completed: NonNegativeInt
    processing_failed: NonNegativeInt
    approval_events: NonNegativeInt
    rejection_events: NonNegativeInt
    reopen_events: NonNegativeInt
    exports_completed: NonNegativeInt
    exports_failed: NonNegativeInt
    average_successful_processing_ms: Duration | None
    median_successful_processing_ms: Duration | None
    successful_processing_sample_count: NonNegativeInt
    processing_duration_integrity_exclusion_count: NonNegativeInt
    initial_validation_pass_rate: Rate | None
    initial_validation_passed_run_count: NonNegativeInt
    initial_validation_eligible_run_count: NonNegativeInt
    initial_validation_incomplete_rule_set_count: NonNegativeInt
    initial_validation_unknown_catalog_count: NonNegativeInt
    failed_extraction_run_count: NonNegativeInt
    review_decision_count: NonNegativeInt
    reviewed_document_count: NonNegativeInt
    approved_cycle_count: NonNegativeInt
    corrected_approval_count: NonNegativeInt
    review_correction_rate: Rate | None
    average_time_to_first_decision_ms: Duration | None
    first_decision_sample_count: NonNegativeInt
    review_timing_integrity_exclusion_count: NonNegativeInt

    @model_validator(mode="after")
    def coherent_metrics(self) -> "PeriodDashboardMetrics":
        if self.review_decision_count != self.approval_events + self.rejection_events:
            raise ValueError("review decision total is inconsistent")
        if self.initial_validation_passed_run_count > self.initial_validation_eligible_run_count:
            raise ValueError("validation numerator exceeds denominator")
        if self.corrected_approval_count > self.approved_cycle_count:
            raise ValueError("correction numerator exceeds denominator")
        pairs = (
            (self.initial_validation_pass_rate, self.initial_validation_eligible_run_count),
            (self.review_correction_rate, self.approved_cycle_count),
        )
        if any((rate is None) != (count == 0) for rate, count in pairs):
            raise ValueError("rate nullability does not match its denominator")
        durations = (self.average_successful_processing_ms, self.median_successful_processing_ms)
        if any(value is None for value in durations) != (self.successful_processing_sample_count == 0):
            raise ValueError("processing duration nullability is inconsistent")
        if (self.average_time_to_first_decision_ms is None) != (self.first_decision_sample_count == 0):
            raise ValueError("review duration nullability is inconsistent")
        return self


class StatusDistributionPoint(Model):
    status: DocumentStatus
    count: NonNegativeInt


class BucketPoint(Model):
    bucket_start: UtcDatetime


class DocumentVolumePoint(BucketPoint):
    uploaded: NonNegativeInt
    processing_completed: NonNegativeInt
    processing_failed: NonNegativeInt


class ReviewDecisionPoint(BucketPoint):
    approved: NonNegativeInt
    rejected: NonNegativeInt
    reopened: NonNegativeInt


class ExportOutcomePoint(BucketPoint):
    completed: NonNegativeInt
    failed: NonNegativeInt


class ProcessingDurationPoint(BucketPoint):
    average_ms: Duration | None
    median_ms: Duration | None
    sample_count: NonNegativeInt
    integrity_exclusion_count: NonNegativeInt

    @model_validator(mode="after")
    def duration_shape(self) -> "ProcessingDurationPoint":
        if any(value is None for value in (self.average_ms, self.median_ms)) != (self.sample_count == 0):
            raise ValueError("duration point nullability is inconsistent")
        return self


class ReviewBacklogPoint(BucketPoint):
    review_backlog_end_of_bucket: NonNegativeInt


class DashboardTrends(Model):
    document_volume: tuple[DocumentVolumePoint, ...]
    review_decisions: tuple[ReviewDecisionPoint, ...]
    export_outcomes: tuple[ExportOutcomePoint, ...]
    successful_processing_duration: tuple[ProcessingDurationPoint, ...]
    review_backlog_end_of_bucket: tuple[ReviewBacklogPoint, ...]

    @model_validator(mode="after")
    def common_spine(self) -> "DashboardTrends":
        series = (
            self.document_volume, self.review_decisions, self.export_outcomes,
            self.successful_processing_duration, self.review_backlog_end_of_bucket,
        )
        spines = [tuple(point.bucket_start for point in points) for points in series]
        if not spines[0] or len(spines[0]) > 366:
            raise ValueError("trend spine must contain 1..366 points")
        if any(spine != spines[0] for spine in spines[1:]):
            raise ValueError("trend series do not share one bucket spine")
        if tuple(sorted(spines[0])) != spines[0] or len(set(spines[0])) != len(spines[0]):
            raise ValueError("trend spine is not strictly ascending")
        return self


class DashboardData(Model):
    definition_version: Literal["dashboard-metrics-v1"] = "dashboard-metrics-v1"
    period: DashboardPeriod
    current: CurrentDashboardMetrics
    period_metrics: PeriodDashboardMetrics
    status_distribution: tuple[StatusDistributionPoint, ...]
    trends: DashboardTrends
    source_status: SourceStatus = SourceStatus()

    @model_validator(mode="after")
    def distribution_integrity(self) -> "DashboardData":
        if tuple(point.status for point in self.status_distribution) != DOCUMENT_STATUSES:
            raise ValueError("status distribution is incomplete or misordered")
        counts = {point.status: point.count for point in self.status_distribution}
        if sum(counts.values()) != self.current.total_documents:
            raise ValueError("status distribution does not sum to total")
        active = sum(counts[name] for name in DOCUMENT_STATUSES[:5])
        if active != self.current.active_processing_documents:
            raise ValueError("active processing total is inconsistent")
        return self


class ActivityItem(Model):
    event_id: Annotated[str, Field(min_length=1, max_length=128)]
    event_type: ActivityEventType
    occurred_at: UtcDatetime
    subject_type: SubjectType
    document_id: UUID | None
    export_id: UUID | None
    actor_user_id: UUID | None
    actor_display_name: ActorName | None
    display_label: PlainLabel
    summary_code: ActivitySummaryCode
    link: RelativeLink | None

    @model_validator(mode="after")
    def valid_subject(self) -> "ActivityItem":
        if self.subject_type == "document":
            if self.document_id is None or self.export_id is not None:
                raise ValueError("document activity has an invalid subject")
        elif self.document_id is not None:
            raise ValueError("export activity cannot expose a document subject")
        return self


class ActivityData(Model):
    snapshot_at: UtcDatetime
    items: tuple[ActivityItem, ...]


class ActivitySuccess(Success[ActivityData]):
    pagination: Pagination


JsonScalar: TypeAlias = str | int | bool | None
JsonValue: TypeAlias = JsonScalar | tuple["JsonValue", ...] | dict[str, "JsonValue"]

__all__ = [name for name in globals() if not name.startswith("_")]
