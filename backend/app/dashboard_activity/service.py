"""Feature 06 metric composition, validation catalog, and role-safe activity."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError

from .errors import DashboardActivityError, invalid
from .repository import (
    DashboardRepository,
    ValidationCatalogRow,
    ValidationRun,
)
from .schemas import (
    ActivityData,
    ActivityItem,
    ActivityQuery,
    ActivitySuccess,
    Bucket,
    Caller,
    CurrentDashboardMetrics,
    DashboardData,
    DashboardPeriod,
    DashboardQuery,
    DashboardTrends,
    DOCUMENT_STATUSES,
    DocumentVolumePoint,
    ExportOutcomePoint,
    Pagination,
    PeriodDashboardMetrics,
    ProcessingDurationPoint,
    ReviewBacklogPoint,
    ReviewDecisionPoint,
    SourceStatus,
    StatusDistributionPoint,
)
from .settings import DashboardActivitySettings


CATALOG_VERSION = "initial-validation-v1"
OPAQUE_VIEWER_EXPORT_ID = re.compile(r"^export_completed:opaque_[0-9a-f]{64}$")
EVENT_SHAPES = {
    "document_uploaded": ("document", "document.uploaded"),
    "processing_completed": ("document", "processing.completed"),
    "processing_failed": ("document", "processing.failed"),
    "review_saved": ("document", "review.field_edited"),
    "document_approved": ("document", "review.approved"),
    "document_rejected": ("document", "review.rejected"),
    "document_reopened": ("document", "review.reopened"),
    "export_requested": ("export", "export.requested"),
    "export_completed": ("export", "export.completed"),
    "export_failed": ("export", "export.failed"),
    "export_expired": ("export", "export.expired"),
}
STATIC_RULES: tuple[tuple[str, str, bool], ...] = (
    ("BR-03-SUBTOTAL", "invoice.subtotal", False),
    ("BR-03-GRAND-TOTAL", "invoice.grand_total", False),
    ("BR-02-REQUIRED", "invoice.invoice_number", False),
    ("BR-02-REQUIRED", "invoice.supplier_name", False),
    ("BR-02-REQUIRED", "invoice.date_issued", False),
    ("BR-02-REQUIRED", "invoice.grand_total", False),
    ("BR-04-EVIDENCE", "invoice.invoice_number", True),
    ("BR-04-EVIDENCE", "invoice.supplier_name", True),
    ("BR-04-EVIDENCE", "invoice.date_issued", True),
    ("BR-04-EVIDENCE", "invoice.currency", True),
    ("BR-04-EVIDENCE", "invoice.subtotal", True),
    ("BR-04-EVIDENCE", "invoice.tax_amount", True),
    ("BR-04-EVIDENCE", "invoice.discount_amount", True),
    ("BR-04-EVIDENCE", "invoice.grand_total", True),
)


class ValidationCatalogProvider(Protocol):
    def expand(self, run: ValidationRun) -> tuple[ValidationCatalogRow, ...] | None:
        """Return the exact immutable rule identities, or None for unknown version."""
        ...


class ProcessingValidationCatalogProvider:
    """Catalog parity adapter for the locked processing validator.

    The static identities mirror ``document_processing_rag.validation``. Dynamic
    line identities are expanded from immutable line ``source_row_key`` values
    loaded in the same database snapshot.
    """

    def __init__(self, supported_pipeline_versions: tuple[str, ...]) -> None:
        versions = tuple(value.strip() for value in supported_pipeline_versions)
        if not versions or any(not value or len(value) > 64 for value in versions):
            raise ValueError("At least one bounded pipeline version is required")
        if len(set(versions)) != len(versions):
            raise ValueError("Pipeline versions must be unique")
        self._versions = frozenset(versions)

    def expand(self, run: ValidationRun) -> tuple[ValidationCatalogRow, ...] | None:
        if run.pipeline_version not in self._versions:
            return None
        if len(set(run.source_row_keys)) != len(run.source_row_keys):
            raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
        rules = list(STATIC_RULES)
        rules.extend(
            ("BR-03-LINE", f"line_items.{source_row_key}", False)
            for source_row_key in run.source_row_keys
        )
        return tuple(
            ValidationCatalogRow(
                extraction_run_id=run.run_id,
                pipeline_version=run.pipeline_version,
                catalog_version=CATALOG_VERSION,
                rule_id=rule_id,
                scope_key=scope_key,
                allows_not_applicable=allows_not_applicable,
            )
            for rule_id, scope_key, allows_not_applicable in rules
        )


def _month_step(value: datetime) -> datetime:
    year, month = value.year, value.month + 1
    if month == 13:
        year, month = year + 1, 1
    return value.replace(year=year, month=month, day=1)


def _floor(value: datetime, bucket: Bucket) -> datetime:
    value = value.astimezone(timezone.utc)
    base = value.replace(hour=0, minute=0, second=0, microsecond=0)
    if bucket == "week":
        return base - timedelta(days=base.weekday())
    if bucket == "month":
        return base.replace(day=1)
    return base


def bucket_spine(from_at: datetime, to_at: datetime, bucket: Bucket) -> tuple[datetime, ...]:
    """Return every UTC bucket touched by the half-open reporting interval."""
    if from_at >= to_at:
        raise invalid("range", "from must be earlier than to.")
    current = _floor(from_at, bucket)
    final = _floor(to_at - timedelta(microseconds=1), bucket)
    result: list[datetime] = []
    while current <= final:
        result.append(current)
        current = _month_step(current) if bucket == "month" else current + timedelta(
            days=7 if bucket == "week" else 1
        )
        if len(result) > 366:
            raise invalid("bucket", "The selected range produces too many buckets.")
    return tuple(result)


def _period(query: DashboardQuery, snapshot_at: datetime,
            settings: DashboardActivitySettings) -> tuple[datetime, datetime, tuple[datetime, ...]]:
    snapshot_at = snapshot_at.astimezone(timezone.utc)
    if query.from_at is None:
        from_at, to_at = snapshot_at - timedelta(days=settings.default_period_days), snapshot_at
    else:
        if query.to_at is None:
            raise invalid("range", "from and to must be supplied together.")
        from_at, to_at = query.from_at, query.to_at
    if to_at > snapshot_at:
        raise invalid("to", "to must not be after the database snapshot.")
    if to_at - from_at > timedelta(days=settings.maximum_period_days):
        raise invalid("range", "The selected range exceeds 366 days.")
    spine = bucket_spine(from_at, to_at, query.bucket)
    if len(spine) > settings.maximum_buckets:
        raise invalid("bucket", "The selected range produces too many buckets.")
    return from_at, to_at, spine


def _pagination(page: int, page_size: int, total: int) -> Pagination:
    total_pages = (total + page_size - 1) // page_size if total else 0
    return Pagination(
        page=page, page_size=page_size, total_records=total,
        total_pages=total_pages, has_next=page < total_pages, has_prev=page > 1,
    )


class AnalyticsService:
    def __init__(self, repository: DashboardRepository,
                 catalog: ValidationCatalogProvider,
                 settings: DashboardActivitySettings) -> None:
        if repository is None or catalog is None or settings is None:
            raise ValueError("Dashboard repository, catalog, and settings are required")
        self._repository = repository
        self._catalog = catalog
        self._settings = settings

    async def get_dashboard(self, caller: Caller, query: DashboardQuery) -> DashboardData:
        if caller.auth_kind != "bearer" or not caller.is_active:
            raise DashboardActivityError("FORBIDDEN")
        try:
            async with self._repository.snapshot() as reader:
                from_at, to_at, expected_spine = _period(query, reader.snapshot_at, self._settings)
                current = await reader.current(caller.company_id)
                period = await reader.period(caller.company_id, from_at, to_at)
                runs = await reader.validation_runs(caller.company_id, from_at, to_at)
                catalog_rows: list[ValidationCatalogRow] = []
                for run in runs:
                    expanded = self._catalog.expand(run)
                    if expanded is not None:
                        catalog_rows.extend(expanded)
                validation = await reader.validation(
                    caller.company_id, from_at, to_at, tuple(catalog_rows),
                )
                review = await reader.review(caller.company_id, from_at, to_at)
                raw = await reader.trends(caller.company_id, from_at, to_at, query.bucket)

                trends = DashboardTrends(
                    document_volume=tuple(DocumentVolumePoint(**row) for row in raw["document_volume"]),
                    review_decisions=tuple(ReviewDecisionPoint(**row) for row in raw["review_decisions"]),
                    export_outcomes=tuple(ExportOutcomePoint(**row) for row in raw["export_outcomes"]),
                    successful_processing_duration=tuple(
                        ProcessingDurationPoint(**row) for row in raw["successful_processing_duration"]
                    ),
                    review_backlog_end_of_bucket=tuple(
                        self._backlog_point(row) for row in raw["review_backlog_end_of_bucket"]
                    ),
                )
                if tuple(point.bucket_start for point in trends.document_volume) != expected_spine:
                    raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
                metrics = PeriodDashboardMetrics(
                    documents_uploaded=period.documents_uploaded,
                    processing_completed=period.processing_completed,
                    processing_failed=period.processing_failed,
                    approval_events=period.approval_events,
                    rejection_events=period.rejection_events,
                    reopen_events=period.reopen_events,
                    exports_completed=period.exports_completed,
                    exports_failed=period.exports_failed,
                    average_successful_processing_ms=period.average_successful_processing_ms,
                    median_successful_processing_ms=period.median_successful_processing_ms,
                    successful_processing_sample_count=period.successful_processing_sample_count,
                    processing_duration_integrity_exclusion_count=period.processing_duration_integrity_exclusion_count,
                    initial_validation_pass_rate=validation.pass_rate,
                    initial_validation_passed_run_count=validation.passed_count,
                    initial_validation_eligible_run_count=validation.eligible_count,
                    initial_validation_incomplete_rule_set_count=validation.incomplete_count,
                    initial_validation_unknown_catalog_count=validation.unknown_catalog_count,
                    failed_extraction_run_count=validation.failed_run_count,
                    review_decision_count=period.approval_events + period.rejection_events,
                    reviewed_document_count=period.reviewed_document_count,
                    approved_cycle_count=review.approval_cycle_count,
                    corrected_approval_count=review.corrected_approval_cycle_count,
                    review_correction_rate=review.correction_rate,
                    average_time_to_first_decision_ms=review.average_time_to_first_decision_ms,
                    first_decision_sample_count=review.first_decision_sample_count,
                    review_timing_integrity_exclusion_count=review.timing_integrity_exclusion_count,
                )
                distribution = tuple(
                    StatusDistributionPoint(status=status, count=current.distribution.get(status, 0))
                    for status in DOCUMENT_STATUSES
                )
                return DashboardData(
                    period=DashboardPeriod(
                        **{"from": from_at, "to": to_at, "bucket": query.bucket,
                           "snapshot_at": reader.snapshot_at}
                    ),
                    current=CurrentDashboardMetrics(
                        total_documents=current.total_documents,
                        active_processing_documents=current.active_processing_documents,
                        pending_review_documents=current.pending_review_documents,
                        approved_documents=current.approved_documents,
                        failed_documents=current.failed_documents,
                        active_export_jobs=current.active_export_jobs,
                    ),
                    period_metrics=metrics,
                    status_distribution=distribution,
                    trends=trends,
                    source_status=SourceStatus(),
                )
        except DashboardActivityError:
            raise
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR") from exc

    @staticmethod
    def _backlog_point(row: dict[str, object]) -> ReviewBacklogPoint:
        if bool(row.get("has_integrity_failure")):
            raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
        value = int(row["review_backlog_end_of_bucket"])
        if value < 0:
            raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
        return ReviewBacklogPoint(
            bucket_start=row["bucket_start"],  # type: ignore[arg-type]
            review_backlog_end_of_bucket=value,
        )


class ActivityService:
    def __init__(self, repository: DashboardRepository,
                 settings: DashboardActivitySettings) -> None:
        if repository is None or settings is None:
            raise ValueError("Activity repository and settings are required")
        self._repository = repository
        self._settings = settings

    async def list_events(self, caller: Caller, query: ActivityQuery) -> tuple[ActivityData, Pagination]:
        if caller.auth_kind != "bearer" or not caller.is_active:
            raise DashboardActivityError("FORBIDDEN")
        try:
            async with self._repository.snapshot() as reader:
                effective = reader.snapshot_at if query.page == 1 else query.snapshot_at
                if effective is None:
                    raise invalid("snapshot_at", "snapshot_at is required after page 1.")
                if effective > reader.snapshot_at:
                    raise invalid("snapshot_at", "snapshot_at must not be in the future.")
                if query.from_at is not None:
                    if query.to_at is None:
                        raise invalid("range", "from and to must be supplied together.")
                    if query.to_at > effective:
                        raise invalid("to", "to must not be after snapshot_at.")
                    if query.to_at - query.from_at > timedelta(days=self._settings.maximum_period_days):
                        raise invalid("range", "The selected range exceeds 366 days.")
                page = await reader.activity(
                    company_id=caller.company_id, role=caller.role,
                    snapshot_at=effective, from_at=query.from_at, to_at=query.to_at,
                    event_types=query.event_type, page=query.page, page_size=query.page_size,
                )
                items = tuple(self._item(caller, item, effective) for item in page.items)
                if page.total_records < len(items):
                    raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
                return ActivityData(snapshot_at=effective, items=items), _pagination(
                    query.page, query.page_size, page.total_records,
                )
        except DashboardActivityError:
            raise
        except (TypeError, ValueError, ValidationError) as exc:
            raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR") from exc

    @staticmethod
    def _item(caller: Caller, record: object, snapshot_at: datetime) -> ActivityItem:
        from .repository import ActivityRecord

        if not isinstance(record, ActivityRecord) or record.occurred_at > snapshot_at:
            raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
        if EVENT_SHAPES.get(record.event_type) != (record.subject_type, record.summary_code):
            raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
        link = f"/documents/{record.document_id}" if record.document_id is not None else None
        if caller.role == "viewer":
            if record.event_type not in {"document_approved", "export_completed"}:
                raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
            if record.actor_user_id is not None or record.actor_display_name is not None or record.export_id is not None:
                raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
            if record.event_type == "export_completed":
                if not OPAQUE_VIEWER_EXPORT_ID.fullmatch(record.event_id) or record.document_id is not None:
                    raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
                link = None
            else:
                prefix, separator, source = record.event_id.partition(":")
                if prefix != record.event_type or not separator:
                    raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
                try:
                    UUID(source)
                except ValueError as exc:
                    raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR") from exc
        else:
            prefix, separator, source = record.event_id.partition(":")
            if prefix != record.event_type or not separator:
                raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
            try:
                UUID(source)
            except ValueError as exc:
                raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR") from exc
        if caller.role == "operator" and record.actor_user_id is not None:
            raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
        return ActivityItem(
            event_id=record.event_id, event_type=record.event_type,
            occurred_at=record.occurred_at, subject_type=record.subject_type,
            document_id=record.document_id, export_id=record.export_id,
            actor_user_id=record.actor_user_id, actor_display_name=record.actor_display_name,
            display_label=record.display_label, summary_code=record.summary_code, link=link,
        )


__all__ = [
    "ActivityService", "AnalyticsService", "ProcessingValidationCatalogProvider",
    "ValidationCatalogProvider", "bucket_spine",
]
