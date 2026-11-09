"""Typed read-only PostgreSQL repository for Feature 06.

The SQL follows the verified database handoff and adds the backend-owned trend,
activity-range, actor-display, and empty-page composition required by the API.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import json
from typing import AsyncIterator, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .errors import DashboardActivityError
from .schemas import (
    ActivityEventType,
    ActivitySummaryCode,
    Bucket,
    DocumentStatus,
    SubjectType,
)


@dataclass(frozen=True)
class CurrentRecord:
    total_documents: int
    active_processing_documents: int
    pending_review_documents: int
    approved_documents: int
    failed_documents: int
    active_export_jobs: int
    distribution: dict[str, int]


@dataclass(frozen=True)
class PeriodRecord:
    documents_uploaded: int
    processing_completed: int
    processing_failed: int
    approval_events: int
    rejection_events: int
    reopen_events: int
    exports_completed: int
    exports_failed: int
    average_successful_processing_ms: int | None
    median_successful_processing_ms: int | None
    successful_processing_sample_count: int
    processing_duration_integrity_exclusion_count: int
    reviewed_document_count: int


@dataclass(frozen=True)
class ValidationRun:
    run_id: UUID
    pipeline_version: str
    source_row_keys: tuple[str, ...]


@dataclass(frozen=True)
class ValidationCatalogRow:
    extraction_run_id: UUID
    pipeline_version: str
    catalog_version: str
    rule_id: str
    scope_key: str
    allows_not_applicable: bool


@dataclass(frozen=True)
class ValidationRecord:
    passed_count: int
    eligible_count: int
    incomplete_count: int
    unknown_catalog_count: int
    pass_rate: Decimal | None
    failed_run_count: int


@dataclass(frozen=True)
class ReviewRecord:
    approval_cycle_count: int
    corrected_approval_cycle_count: int
    correction_rate: Decimal | None
    first_decision_sample_count: int
    average_time_to_first_decision_ms: int | None
    timing_integrity_exclusion_count: int


@dataclass(frozen=True)
class ActivityRecord:
    event_id: str
    event_type: ActivityEventType
    occurred_at: datetime
    subject_type: SubjectType
    document_id: UUID | None
    export_id: UUID | None
    actor_user_id: UUID | None
    actor_display_name: str | None
    display_label: str
    summary_code: ActivitySummaryCode


@dataclass(frozen=True)
class ActivityPageRecord:
    items: tuple[ActivityRecord, ...]
    total_records: int


Row = dict[str, object]


class DashboardSnapshotReader(Protocol):
    snapshot_at: datetime

    async def current(self, company_id: UUID) -> CurrentRecord: ...
    async def period(self, company_id: UUID, from_at: datetime, to_at: datetime) -> PeriodRecord: ...
    async def validation_runs(self, company_id: UUID, from_at: datetime, to_at: datetime) -> tuple[ValidationRun, ...]: ...
    async def validation(self, company_id: UUID, from_at: datetime, to_at: datetime,
                         catalog: tuple[ValidationCatalogRow, ...]) -> ValidationRecord: ...
    async def review(self, company_id: UUID, from_at: datetime, to_at: datetime) -> ReviewRecord: ...
    async def trends(self, company_id: UUID, from_at: datetime, to_at: datetime,
                     bucket: Bucket) -> dict[str, tuple[Row, ...]]: ...
    async def activity(self, *, company_id: UUID, role: str,
                       snapshot_at: datetime, from_at: datetime | None,
                       to_at: datetime | None, event_types: tuple[ActivityEventType, ...],
                       page: int, page_size: int) -> ActivityPageRecord: ...


class DashboardRepository(Protocol):
    @asynccontextmanager
    async def snapshot(self) -> AsyncIterator[DashboardSnapshotReader]: ...


STATUS_SQL = """
WITH status_counts AS (
  SELECT d.status, count(*)::bigint AS item_count
  FROM documents d WHERE d.company_id=CAST(:company_id AS uuid)
  GROUP BY d.status
), expected(status, ordinal) AS (
  VALUES ('queued',1),('partitioning',2),('chunking',3),('vectorizing',4),
         ('extracting',5),('pending_review',6),('approved',7),('rejected',8),('failed',9)
), distribution AS (
  SELECT e.status,e.ordinal,COALESCE(s.item_count,0)::bigint AS item_count
  FROM expected e LEFT JOIN status_counts s USING(status)
), exports AS (
  SELECT count(*)::bigint AS active_export_jobs FROM export_jobs e
  WHERE e.company_id=CAST(:company_id AS uuid) AND e.mode='asynchronous'
    AND e.status IN ('queued','processing')
), unknowns AS (
  SELECT count(*)::bigint AS item_count FROM status_counts s
  WHERE NOT EXISTS (SELECT 1 FROM expected e WHERE e.status=s.status)
)
SELECT sum(d.item_count)::bigint AS total_documents,
  sum(d.item_count) FILTER (WHERE d.ordinal<=5)::bigint AS active_processing_documents,
  sum(d.item_count) FILTER (WHERE d.status='pending_review')::bigint AS pending_review_documents,
  sum(d.item_count) FILTER (WHERE d.status='approved')::bigint AS approved_documents,
  sum(d.item_count) FILTER (WHERE d.status='failed')::bigint AS failed_documents,
  (SELECT active_export_jobs FROM exports) AS active_export_jobs,
  (SELECT item_count FROM unknowns) AS unknown_status_count,
  jsonb_object_agg(d.status,d.item_count ORDER BY d.ordinal) AS status_distribution
FROM distribution d
"""

PERIOD_SQL = """
WITH tenant_documents AS MATERIALIZED (
  SELECT id FROM documents WHERE company_id=CAST(:company_id AS uuid)
), uploads AS (
  SELECT count(*)::bigint AS uploaded FROM documents
  WHERE company_id=CAST(:company_id AS uuid)
    AND created_at>=CAST(:from_at AS timestamptz) AND created_at<CAST(:to_at AS timestamptz)
), jobs AS (
  SELECT count(*) FILTER (WHERE j.status='completed')::bigint AS processing_completed,
    count(*) FILTER (WHERE j.status='failed')::bigint AS processing_failed,
    count(*) FILTER (WHERE j.status='completed' AND j.started_at IS NOT NULL
      AND j.finished_at>=j.started_at)::bigint AS successful_processing_sample_count,
    count(*) FILTER (WHERE j.status='completed' AND
      (j.started_at IS NULL OR j.finished_at<j.started_at))::bigint
      AS processing_duration_integrity_exclusion_count,
    round(avg(extract(epoch FROM (j.finished_at-j.started_at))*1000)
      FILTER (WHERE j.status='completed' AND j.started_at IS NOT NULL
        AND j.finished_at>=j.started_at))::bigint AS average_successful_processing_ms,
    round(percentile_cont(0.5) WITHIN GROUP (
      ORDER BY extract(epoch FROM (j.finished_at-j.started_at))*1000)
      FILTER (WHERE j.status='completed' AND j.started_at IS NOT NULL
        AND j.finished_at>=j.started_at))::bigint AS median_successful_processing_ms
  FROM processing_jobs j JOIN tenant_documents d ON d.id=j.document_id
  WHERE j.status IN ('completed','failed')
    AND j.finished_at>=CAST(:from_at AS timestamptz) AND j.finished_at<CAST(:to_at AS timestamptz)
), reviews AS (
  SELECT count(*) FILTER (WHERE r.action='approved')::bigint AS review_approved,
    count(*) FILTER (WHERE r.action='rejected')::bigint AS review_rejected,
    count(*) FILTER (WHERE r.action='reopened')::bigint AS review_reopened,
    count(DISTINCT r.document_id) FILTER (WHERE r.action IN ('approved','rejected'))::bigint
      AS reviewed_document_count
  FROM review_audit_events r JOIN tenant_documents d ON d.id=r.document_id
  WHERE r.action IN ('approved','rejected','reopened')
    AND r.created_at>=CAST(:from_at AS timestamptz) AND r.created_at<CAST(:to_at AS timestamptz)
), exports AS (
  SELECT count(*) FILTER (WHERE e.completed_at>=CAST(:from_at AS timestamptz)
      AND e.completed_at<CAST(:to_at AS timestamptz))::bigint AS export_completed,
    count(*) FILTER (WHERE e.failed_at>=CAST(:from_at AS timestamptz)
      AND e.failed_at<CAST(:to_at AS timestamptz))::bigint AS export_failed
  FROM export_jobs e WHERE e.company_id=CAST(:company_id AS uuid)
)
SELECT * FROM uploads CROSS JOIN jobs CROSS JOIN reviews CROSS JOIN exports
"""

VALIDATION_RUNS_SQL = """
SELECT r.id AS run_id,r.pipeline_version,
  COALESCE(jsonb_agg(li.source_row_key ORDER BY li.line_order)
    FILTER (WHERE li.id IS NOT NULL),'[]'::jsonb) AS source_row_keys
FROM extraction_runs r
JOIN documents d ON d.id=r.document_id
LEFT JOIN invoices i ON i.extraction_run_id=r.id
LEFT JOIN line_items li ON li.invoice_id=i.id
WHERE d.company_id=CAST(:company_id AS uuid) AND r.status='completed'
  AND r.finished_at>=CAST(:from_at AS timestamptz) AND r.finished_at<CAST(:to_at AS timestamptz)
GROUP BY r.id,r.pipeline_version ORDER BY r.id
"""

VALIDATION_SQL = """
WITH catalog AS MATERIALIZED (
  SELECT c.extraction_run_id,c.pipeline_version,c.rule_id,c.scope_key,c.allows_not_applicable
  FROM jsonb_to_recordset(CAST(:validation_catalog_json AS jsonb)) AS c(
    extraction_run_id uuid,pipeline_version text,catalog_version text,
    rule_id text,scope_key text,allows_not_applicable boolean)
), candidates AS MATERIALIZED (
  SELECT r.id,r.pipeline_version FROM extraction_runs r JOIN documents d ON d.id=r.document_id
  WHERE d.company_id=CAST(:company_id AS uuid) AND r.status='completed'
    AND r.finished_at>=CAST(:from_at AS timestamptz) AND r.finished_at<CAST(:to_at AS timestamptz)
), sizes AS (
  SELECT extraction_run_id,count(*)::integer AS required_count FROM catalog GROUP BY extraction_run_id
), evaluated AS (
  SELECT r.id,COALESCE(s.required_count,0)::integer AS required_count,
    count(v.id) FILTER (WHERE c.rule_id IS NOT NULL)::integer AS matched_count,
    count(v.id) FILTER (WHERE c.rule_id IS NOT NULL AND
      (v.status='passed' OR (v.status='not_applicable' AND c.allows_not_applicable)))::integer AS passing_count,
    count(v.id) FILTER (WHERE c.rule_id IS NULL)::integer AS unexpected_count
  FROM candidates r LEFT JOIN sizes s ON s.extraction_run_id=r.id
  LEFT JOIN validation_results v ON v.extraction_run_id=r.id
  LEFT JOIN catalog c ON c.extraction_run_id=r.id AND c.pipeline_version=r.pipeline_version
    AND c.rule_id=v.rule_id AND c.scope_key=v.scope_key
  GROUP BY r.id,s.required_count
), failed AS (
  SELECT count(*)::bigint AS failed_run_count FROM extraction_runs r
  JOIN documents d ON d.id=r.document_id
  WHERE d.company_id=CAST(:company_id AS uuid) AND r.status='failed'
    AND r.finished_at>=CAST(:from_at AS timestamptz) AND r.finished_at<CAST(:to_at AS timestamptz)
)
SELECT count(*) FILTER (WHERE required_count>0 AND matched_count=required_count
    AND passing_count=required_count AND unexpected_count=0)::bigint AS passed_count,
  count(*) FILTER (WHERE required_count>0 AND matched_count=required_count
    AND unexpected_count=0)::bigint AS eligible_count,
  count(*) FILTER (WHERE required_count>0 AND
    (matched_count<>required_count OR unexpected_count<>0))::bigint AS incomplete_count,
  count(*) FILTER (WHERE required_count=0)::bigint AS unknown_catalog_count,
  round(100.0*count(*) FILTER (WHERE required_count>0 AND matched_count=required_count
      AND passing_count=required_count AND unexpected_count=0)
    / NULLIF(count(*) FILTER (WHERE required_count>0 AND matched_count=required_count
      AND unexpected_count=0),0),2) AS pass_rate,
  (SELECT failed_run_count FROM failed) AS failed_run_count
FROM evaluated
"""

REVIEW_SQL = """
WITH tenant_documents AS MATERIALIZED (
  SELECT id FROM documents WHERE company_id=CAST(:company_id AS uuid)
), initial_success AS MATERIALIZED (
  SELECT j.document_id,j.finished_at FROM processing_jobs j
  JOIN tenant_documents d ON d.id=j.document_id WHERE j.status='completed'
), all_terminal AS MATERIALIZED (
  SELECT r.id,r.document_id,r.action,r.review_revision,r.created_at
  FROM review_audit_events r JOIN tenant_documents d ON d.id=r.document_id
  WHERE r.action IN ('approved','rejected')
), terminal AS MATERIALIZED (
  SELECT r.*,COALESCE((SELECT max(x.review_revision) FROM review_audit_events x
    WHERE x.document_id=r.document_id AND x.action='reopened'
      AND (x.review_revision,x.created_at,x.id)<(r.review_revision,r.created_at,r.id)),0)::bigint
      AS lower_revision
  FROM all_terminal r WHERE r.created_at>=CAST(:from_at AS timestamptz)
    AND r.created_at<CAST(:to_at AS timestamptz)
), cycles AS (
  SELECT t.*,EXISTS(SELECT 1 FROM review_audit_changes c
    JOIN review_audit_events e ON e.id=c.audit_event_id
    WHERE e.document_id=t.document_id AND e.review_revision>t.lower_revision
      AND e.review_revision<=t.review_revision) AS corrected
  FROM terminal t
), first_decisions AS (
  SELECT DISTINCT ON (t.document_id) t.document_id,t.created_at AS decision_at,s.finished_at
  FROM all_terminal t LEFT JOIN initial_success s ON s.document_id=t.document_id
  ORDER BY t.document_id,t.review_revision,t.created_at,t.id
)
SELECT count(*) FILTER (WHERE c.action='approved')::bigint AS approval_cycle_count,
  count(*) FILTER (WHERE c.action='approved' AND c.corrected)::bigint AS corrected_count,
  round(100.0*count(*) FILTER (WHERE c.action='approved' AND c.corrected)
    / NULLIF(count(*) FILTER (WHERE c.action='approved'),0),2) AS correction_rate,
  (SELECT count(*) FROM first_decisions f WHERE f.decision_at>=CAST(:from_at AS timestamptz)
    AND f.decision_at<CAST(:to_at AS timestamptz) AND f.finished_at IS NOT NULL
    AND f.decision_at>=f.finished_at)::bigint AS first_decision_sample_count,
  (SELECT round(avg(extract(epoch FROM (f.decision_at-f.finished_at))*1000))::bigint
    FROM first_decisions f WHERE f.decision_at>=CAST(:from_at AS timestamptz)
      AND f.decision_at<CAST(:to_at AS timestamptz) AND f.finished_at IS NOT NULL
      AND f.decision_at>=f.finished_at) AS average_time_to_first_decision_ms,
  (SELECT count(*) FROM first_decisions f WHERE f.decision_at>=CAST(:from_at AS timestamptz)
    AND f.decision_at<CAST(:to_at AS timestamptz)
    AND (f.finished_at IS NULL OR f.decision_at<f.finished_at))::bigint AS timing_exclusion_count
FROM cycles c
"""

SPINE = """
parameters AS (SELECT CAST(:company_id AS uuid) company_id,
  CAST(:from_at AS timestamptz) from_at,CAST(:to_at AS timestamptz) to_at,
  CAST(:bucket AS text) bucket),
spine AS (SELECT generate_series(
  CASE bucket WHEN 'day' THEN date_trunc('day',from_at) WHEN 'week' THEN date_trunc('week',from_at)
    ELSE date_trunc('month',from_at) END,
  CASE bucket WHEN 'day' THEN date_trunc('day',to_at-interval '1 microsecond')
    WHEN 'week' THEN date_trunc('week',to_at-interval '1 microsecond')
    ELSE date_trunc('month',to_at-interval '1 microsecond') END,
  CASE bucket WHEN 'day' THEN interval '1 day' WHEN 'week' THEN interval '1 week'
    ELSE interval '1 month' END) AS bucket_start FROM parameters)
"""

DOCUMENT_TREND_SQL = f"""
WITH {SPINE}, events AS (
  SELECT d.created_at occurred_at,1::bigint uploaded,0::bigint completed,0::bigint failed
  FROM documents d,parameters p WHERE d.company_id=p.company_id AND d.created_at>=p.from_at AND d.created_at<p.to_at
  UNION ALL
  SELECT j.finished_at,0,(j.status='completed')::int,(j.status='failed')::int
  FROM processing_jobs j JOIN documents d ON d.id=j.document_id JOIN parameters p ON p.company_id=d.company_id
  WHERE j.status IN ('completed','failed') AND j.finished_at>=p.from_at AND j.finished_at<p.to_at
), grouped AS (SELECT CASE p.bucket WHEN 'day' THEN date_trunc('day',e.occurred_at)
    WHEN 'week' THEN date_trunc('week',e.occurred_at) ELSE date_trunc('month',e.occurred_at) END bucket_start,
  sum(uploaded)::bigint uploaded,sum(completed)::bigint processing_completed,sum(failed)::bigint processing_failed
  FROM events e CROSS JOIN parameters p GROUP BY 1)
SELECT s.bucket_start,COALESCE(g.uploaded,0)::bigint uploaded,
  COALESCE(g.processing_completed,0)::bigint processing_completed,
  COALESCE(g.processing_failed,0)::bigint processing_failed
FROM spine s LEFT JOIN grouped g USING(bucket_start) ORDER BY s.bucket_start
"""

REVIEW_TREND_SQL = f"""
WITH {SPINE}, grouped AS (SELECT CASE p.bucket WHEN 'day' THEN date_trunc('day',r.created_at)
    WHEN 'week' THEN date_trunc('week',r.created_at) ELSE date_trunc('month',r.created_at) END bucket_start,
  count(*) FILTER (WHERE r.action='approved')::bigint approved,
  count(*) FILTER (WHERE r.action='rejected')::bigint rejected,
  count(*) FILTER (WHERE r.action='reopened')::bigint reopened
  FROM review_audit_events r JOIN documents d ON d.id=r.document_id
  JOIN parameters p ON p.company_id=d.company_id
  WHERE r.action IN ('approved','rejected','reopened') AND r.created_at>=p.from_at AND r.created_at<p.to_at
  GROUP BY 1)
SELECT s.bucket_start,COALESCE(g.approved,0)::bigint approved,
  COALESCE(g.rejected,0)::bigint rejected,COALESCE(g.reopened,0)::bigint reopened
FROM spine s LEFT JOIN grouped g USING(bucket_start) ORDER BY s.bucket_start
"""

EXPORT_TREND_SQL = f"""
WITH {SPINE}, events AS (
  SELECT e.completed_at occurred_at,1::bigint completed,0::bigint failed FROM export_jobs e,parameters p
  WHERE e.company_id=p.company_id AND e.completed_at>=p.from_at AND e.completed_at<p.to_at
  UNION ALL
  SELECT e.failed_at,0,1 FROM export_jobs e,parameters p
  WHERE e.company_id=p.company_id AND e.failed_at>=p.from_at AND e.failed_at<p.to_at
), grouped AS (SELECT CASE p.bucket WHEN 'day' THEN date_trunc('day',e.occurred_at)
    WHEN 'week' THEN date_trunc('week',e.occurred_at) ELSE date_trunc('month',e.occurred_at) END bucket_start,
  sum(completed)::bigint completed,sum(failed)::bigint failed FROM events e CROSS JOIN parameters p GROUP BY 1)
SELECT s.bucket_start,COALESCE(g.completed,0)::bigint completed,COALESCE(g.failed,0)::bigint failed
FROM spine s LEFT JOIN grouped g USING(bucket_start) ORDER BY s.bucket_start
"""

DURATION_TREND_SQL = f"""
WITH {SPINE}, grouped AS (SELECT CASE p.bucket WHEN 'day' THEN date_trunc('day',j.finished_at)
    WHEN 'week' THEN date_trunc('week',j.finished_at) ELSE date_trunc('month',j.finished_at) END bucket_start,
  round(avg(extract(epoch FROM (j.finished_at-j.started_at))*1000)
    FILTER (WHERE j.started_at IS NOT NULL AND j.finished_at>=j.started_at))::bigint average_ms,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM (j.finished_at-j.started_at))*1000)
    FILTER (WHERE j.started_at IS NOT NULL AND j.finished_at>=j.started_at))::bigint median_ms,
  count(*) FILTER (WHERE j.started_at IS NOT NULL AND j.finished_at>=j.started_at)::bigint sample_count,
  count(*) FILTER (WHERE j.started_at IS NULL OR j.finished_at<j.started_at)::bigint integrity_exclusion_count
  FROM processing_jobs j JOIN documents d ON d.id=j.document_id
  JOIN parameters p ON p.company_id=d.company_id
  WHERE j.status='completed' AND j.finished_at>=p.from_at AND j.finished_at<p.to_at GROUP BY 1)
SELECT s.bucket_start,g.average_ms,g.median_ms,COALESCE(g.sample_count,0)::bigint sample_count,
  COALESCE(g.integrity_exclusion_count,0)::bigint integrity_exclusion_count
FROM spine s LEFT JOIN grouped g USING(bucket_start) ORDER BY s.bucket_start
"""

BACKLOG_SQL = f"""
WITH {SPINE}, event_stream AS MATERIALIZED (
  SELECT j.finished_at occurred_at,1::bigint delta FROM processing_jobs j
  JOIN documents d ON d.id=j.document_id JOIN parameters p ON p.company_id=d.company_id
  WHERE j.status='completed' AND j.finished_at<p.to_at
  UNION ALL SELECT r.created_at,CASE WHEN r.action='reopened' THEN 1::bigint ELSE -1::bigint END
  FROM review_audit_events r JOIN documents d ON d.id=r.document_id
  JOIN parameters p ON p.company_id=d.company_id
  WHERE r.action IN ('approved','rejected','reopened') AND r.created_at<p.to_at
), opening AS (SELECT COALESCE(sum(e.delta) FILTER (WHERE e.occurred_at<p.from_at),0)::bigint balance
  FROM event_stream e CROSS JOIN parameters p), bucketed AS (
  SELECT CASE p.bucket WHEN 'day' THEN date_trunc('day',e.occurred_at)
    WHEN 'week' THEN date_trunc('week',e.occurred_at) ELSE date_trunc('month',e.occurred_at) END bucket_start,
    sum(e.delta)::bigint delta FROM event_stream e CROSS JOIN parameters p
  WHERE e.occurred_at>=p.from_at AND e.occurred_at<p.to_at GROUP BY 1
), event_deltas AS (SELECT occurred_at,sum(delta)::bigint delta FROM event_stream GROUP BY occurred_at),
integrity AS (SELECT COALESCE(min(balance),0)<0 has_integrity_failure FROM (
  SELECT sum(delta) OVER (ORDER BY occurred_at ROWS UNBOUNDED PRECEDING) balance FROM event_deltas) q),
balances AS (SELECT s.bucket_start,o.balance+sum(COALESCE(b.delta,0)) OVER
  (ORDER BY s.bucket_start ROWS UNBOUNDED PRECEDING) review_backlog_end_of_bucket
  FROM spine s CROSS JOIN opening o LEFT JOIN bucketed b USING(bucket_start))
SELECT b.bucket_start,b.review_backlog_end_of_bucket::bigint,i.has_integrity_failure
FROM balances b CROSS JOIN integrity i ORDER BY b.bucket_start
"""

ADMIN_ACTIVITY_SQL = """
WITH activity AS (
  SELECT d.id source_uuid,'document_uploaded'::text event_type,d.created_at occurred_at,
    'document'::text subject_type,d.id document_id,NULL::uuid export_id,d.uploaded_by actor_user_id,
    left(d.file_name,255) display_label,'document.uploaded'::text summary_code
  FROM documents d WHERE d.company_id=CAST(:company_id AS uuid)
  UNION ALL SELECT j.id,CASE j.status WHEN 'completed' THEN 'processing_completed' ELSE 'processing_failed' END,
    j.finished_at,'document',d.id,NULL::uuid,NULL::uuid,left(d.file_name,255),
    CASE j.status WHEN 'completed' THEN 'processing.completed' ELSE 'processing.failed' END
  FROM processing_jobs j JOIN documents d ON d.id=j.document_id
  WHERE d.company_id=CAST(:company_id AS uuid) AND j.status IN ('completed','failed')
  UNION ALL SELECT r.id,CASE r.action WHEN 'field_edited' THEN 'review_saved'
    WHEN 'approved' THEN 'document_approved' WHEN 'rejected' THEN 'document_rejected'
    ELSE 'document_reopened' END,r.created_at,'document',d.id,NULL::uuid,r.actor_user_id,
    left(d.file_name,255),'review.'||r.action
  FROM review_audit_events r JOIN documents d ON d.id=r.document_id
  WHERE d.company_id=CAST(:company_id AS uuid) AND r.action IN ('field_edited','approved','rejected','reopened')
  UNION ALL SELECT e.id,x.event_type,x.occurred_at,'export',NULL::uuid,e.id,e.requested_by_user_id,
    'Export','export.'||x.suffix FROM export_jobs e CROSS JOIN LATERAL (VALUES
      ('export_requested'::text,e.created_at,'requested'::text),('export_completed',e.completed_at,'completed'),
      ('export_failed',e.failed_at,'failed'),('export_expired',e.expired_at,'expired')) x(event_type,occurred_at,suffix)
  WHERE e.company_id=CAST(:company_id AS uuid) AND x.occurred_at IS NOT NULL
), visible AS (
  SELECT a.*,a.event_type||':'||a.source_uuid::text event_id FROM activity a
  WHERE a.occurred_at<=CAST(:snapshot_at AS timestamptz)
    AND (CAST(:from_at AS timestamptz) IS NULL OR a.occurred_at>=CAST(:from_at AS timestamptz))
    AND (CAST(:to_at AS timestamptz) IS NULL OR a.occurred_at<CAST(:to_at AS timestamptz))
    AND (CAST(:event_types_json AS jsonb)='[]'::jsonb OR a.event_type IN
      (SELECT jsonb_array_elements_text(CAST(:event_types_json AS jsonb))))
), enriched AS (
  SELECT v.*,u.full_name actor_display_name FROM visible v LEFT JOIN users u
    ON u.id=v.actor_user_id AND u.company_id=CAST(:company_id AS uuid)
), total AS (SELECT count(*)::bigint total_count FROM enriched), page_rows AS (
  SELECT * FROM enriched ORDER BY occurred_at DESC,event_type ASC,source_uuid DESC
  LIMIT CAST(:page_size AS integer) OFFSET (CAST(:page AS integer)-1)*CAST(:page_size AS integer))
SELECT p.event_id,p.event_type,p.occurred_at,p.subject_type,p.document_id,p.export_id,
  CASE WHEN CAST(:include_actor_id AS boolean) THEN p.actor_user_id ELSE NULL::uuid END actor_user_id,
  p.actor_display_name,p.display_label,p.summary_code,t.total_count
FROM total t LEFT JOIN page_rows p ON true
ORDER BY p.occurred_at DESC,p.event_type ASC,p.source_uuid DESC
"""

VIEWER_ACTIVITY_SQL = """
WITH activity AS (
  SELECT r.id source_uuid,'document_approved'::text event_type,r.created_at occurred_at,
    'document'::text subject_type,d.id document_id,left(d.file_name,255) display_label,
    'review.approved'::text summary_code
  FROM review_audit_events r JOIN documents d ON d.id=r.document_id
  WHERE d.company_id=CAST(:company_id AS uuid) AND d.status='approved' AND r.action='approved'
  UNION ALL SELECT e.id,'export_completed',e.completed_at,'export',NULL::uuid,
    'Export completed','export.completed' FROM export_jobs e
  WHERE e.company_id=CAST(:company_id AS uuid) AND e.completed_at IS NOT NULL
), visible AS (
  SELECT a.*,CASE WHEN a.event_type='export_completed' THEN
    'export_completed:opaque_'||encode(digest(convert_to('docusense-activity-viewer-v1','UTF8')||decode('00','hex')||
      convert_to(CAST(:company_id AS uuid)::text,'UTF8')||decode('00','hex')||
      convert_to('export_completed','UTF8')||decode('00','hex')||convert_to(a.source_uuid::text,'UTF8'),'sha256'),'hex')
    ELSE a.event_type||':'||a.source_uuid::text END event_id
  FROM activity a WHERE a.occurred_at<=CAST(:snapshot_at AS timestamptz)
    AND (CAST(:from_at AS timestamptz) IS NULL OR a.occurred_at>=CAST(:from_at AS timestamptz))
    AND (CAST(:to_at AS timestamptz) IS NULL OR a.occurred_at<CAST(:to_at AS timestamptz))
    AND (CAST(:event_types_json AS jsonb)='[]'::jsonb OR a.event_type IN
      (SELECT jsonb_array_elements_text(CAST(:event_types_json AS jsonb))))
), total AS (SELECT count(*)::bigint total_count FROM visible), page_rows AS (
  SELECT * FROM visible ORDER BY occurred_at DESC,event_type ASC,source_uuid DESC
  LIMIT CAST(:page_size AS integer) OFFSET (CAST(:page AS integer)-1)*CAST(:page_size AS integer))
SELECT p.event_id,p.event_type,p.occurred_at,p.subject_type,p.document_id,NULL::uuid export_id,
  NULL::uuid actor_user_id,NULL::text actor_display_name,p.display_label,p.summary_code,t.total_count
FROM total t LEFT JOIN page_rows p ON true
ORDER BY p.occurred_at DESC,p.event_type ASC,p.source_uuid DESC
"""


def _mapping(row: object) -> Row:
    return dict(row)  # type: ignore[arg-type]


def _count(value: object) -> int:
    return int(value or 0)


class SqlDashboardSnapshot:
    def __init__(self, session: AsyncSession, snapshot_at: datetime) -> None:
        self._session = session
        self.snapshot_at = snapshot_at

    async def _one(self, statement: str, parameters: dict[str, object]) -> Row:
        result = await self._session.execute(text(statement), parameters)
        return _mapping(result.mappings().one())

    async def _all(self, statement: str, parameters: dict[str, object]) -> tuple[Row, ...]:
        result = await self._session.execute(text(statement), parameters)
        return tuple(_mapping(row) for row in result.mappings().all())

    async def current(self, company_id: UUID) -> CurrentRecord:
        row = await self._one(STATUS_SQL, {"company_id": company_id})
        if _count(row["unknown_status_count"]):
            raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
        raw_distribution = row["status_distribution"]
        if not isinstance(raw_distribution, dict):
            raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
        return CurrentRecord(
            total_documents=_count(row["total_documents"]),
            active_processing_documents=_count(row["active_processing_documents"]),
            pending_review_documents=_count(row["pending_review_documents"]),
            approved_documents=_count(row["approved_documents"]),
            failed_documents=_count(row["failed_documents"]),
            active_export_jobs=_count(row["active_export_jobs"]),
            distribution={str(key): _count(value) for key, value in raw_distribution.items()},
        )

    async def period(self, company_id: UUID, from_at: datetime, to_at: datetime) -> PeriodRecord:
        row = await self._one(PERIOD_SQL, {"company_id": company_id, "from_at": from_at, "to_at": to_at})
        return PeriodRecord(
            documents_uploaded=_count(row["uploaded"]),
            processing_completed=_count(row["processing_completed"]),
            processing_failed=_count(row["processing_failed"]),
            approval_events=_count(row["review_approved"]),
            rejection_events=_count(row["review_rejected"]),
            reopen_events=_count(row["review_reopened"]),
            exports_completed=_count(row["export_completed"]),
            exports_failed=_count(row["export_failed"]),
            average_successful_processing_ms=None if row["average_successful_processing_ms"] is None else int(row["average_successful_processing_ms"]),
            median_successful_processing_ms=None if row["median_successful_processing_ms"] is None else int(row["median_successful_processing_ms"]),
            successful_processing_sample_count=_count(row["successful_processing_sample_count"]),
            processing_duration_integrity_exclusion_count=_count(row["processing_duration_integrity_exclusion_count"]),
            reviewed_document_count=_count(row["reviewed_document_count"]),
        )

    async def validation_runs(self, company_id: UUID, from_at: datetime,
                              to_at: datetime) -> tuple[ValidationRun, ...]:
        rows = await self._all(VALIDATION_RUNS_SQL, {"company_id": company_id, "from_at": from_at, "to_at": to_at})
        result: list[ValidationRun] = []
        for row in rows:
            keys = row["source_row_keys"]
            if not isinstance(keys, list) or any(not isinstance(key, str) for key in keys):
                raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
            result.append(ValidationRun(
                run_id=UUID(str(row["run_id"])), pipeline_version=str(row["pipeline_version"]),
                source_row_keys=tuple(keys),
            ))
        return tuple(result)

    async def validation(self, company_id: UUID, from_at: datetime, to_at: datetime,
                         catalog: tuple[ValidationCatalogRow, ...]) -> ValidationRecord:
        payload = [{
            "extraction_run_id": str(item.extraction_run_id),
            "pipeline_version": item.pipeline_version,
            "catalog_version": item.catalog_version,
            "rule_id": item.rule_id,
            "scope_key": item.scope_key,
            "allows_not_applicable": item.allows_not_applicable,
        } for item in catalog]
        row = await self._one(VALIDATION_SQL, {
            "company_id": company_id, "from_at": from_at, "to_at": to_at,
            "validation_catalog_json": json.dumps(payload, separators=(",", ":")),
        })
        rate = row["pass_rate"]
        return ValidationRecord(
            passed_count=_count(row["passed_count"]), eligible_count=_count(row["eligible_count"]),
            incomplete_count=_count(row["incomplete_count"]), unknown_catalog_count=_count(row["unknown_catalog_count"]),
            pass_rate=None if rate is None else Decimal(str(rate)), failed_run_count=_count(row["failed_run_count"]),
        )

    async def review(self, company_id: UUID, from_at: datetime, to_at: datetime) -> ReviewRecord:
        row = await self._one(REVIEW_SQL, {"company_id": company_id, "from_at": from_at, "to_at": to_at})
        rate = row["correction_rate"]
        return ReviewRecord(
            approval_cycle_count=_count(row["approval_cycle_count"]),
            corrected_approval_cycle_count=_count(row["corrected_count"]),
            correction_rate=None if rate is None else Decimal(str(rate)),
            first_decision_sample_count=_count(row["first_decision_sample_count"]),
            average_time_to_first_decision_ms=None if row["average_time_to_first_decision_ms"] is None else int(row["average_time_to_first_decision_ms"]),
            timing_integrity_exclusion_count=_count(row["timing_exclusion_count"]),
        )

    async def trends(self, company_id: UUID, from_at: datetime, to_at: datetime,
                     bucket: Bucket) -> dict[str, tuple[Row, ...]]:
        parameters: dict[str, object] = {
            "company_id": company_id, "from_at": from_at, "to_at": to_at, "bucket": bucket,
        }
        statements = {
            "document_volume": DOCUMENT_TREND_SQL,
            "review_decisions": REVIEW_TREND_SQL,
            "export_outcomes": EXPORT_TREND_SQL,
            "successful_processing_duration": DURATION_TREND_SQL,
            "review_backlog_end_of_bucket": BACKLOG_SQL,
        }
        return {name: await self._all(statement, parameters) for name, statement in statements.items()}

    async def activity(self, *, company_id: UUID, role: str, snapshot_at: datetime,
                       from_at: datetime | None, to_at: datetime | None,
                       event_types: tuple[ActivityEventType, ...], page: int,
                       page_size: int) -> ActivityPageRecord:
        statement = VIEWER_ACTIVITY_SQL if role == "viewer" else ADMIN_ACTIVITY_SQL
        rows = await self._all(statement, {
            "company_id": company_id, "snapshot_at": snapshot_at,
            "from_at": from_at, "to_at": to_at,
            "event_types_json": json.dumps(event_types), "page": page,
            "page_size": page_size, "include_actor_id": role == "admin",
        })
        total = _count(rows[0]["total_count"]) if rows else 0
        items: list[ActivityRecord] = []
        for row in rows:
            if row["event_id"] is None:
                continue
            items.append(ActivityRecord(
                event_id=str(row["event_id"]), event_type=str(row["event_type"]),  # type: ignore[arg-type]
                occurred_at=row["occurred_at"], subject_type=str(row["subject_type"]),  # type: ignore[arg-type]
                document_id=None if row["document_id"] is None else UUID(str(row["document_id"])),
                export_id=None if row["export_id"] is None else UUID(str(row["export_id"])),
                actor_user_id=None if row["actor_user_id"] is None else UUID(str(row["actor_user_id"])),
                actor_display_name=None if row["actor_display_name"] is None else str(row["actor_display_name"]),
                display_label=str(row["display_label"]), summary_code=str(row["summary_code"]),  # type: ignore[arg-type]
            ))
        return ActivityPageRecord(tuple(items), total)


class SqlDashboardRepository:
    """Create one read-only repeatable-read unit of work per API request."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], *,
                 statement_timeout_ms: int = 2_000) -> None:
        if sessions is None or not 100 <= statement_timeout_ms <= 30_000:
            raise ValueError("A session factory and bounded timeout are required")
        self._sessions = sessions
        self._statement_timeout_ms = statement_timeout_ms

    @asynccontextmanager
    async def snapshot(self) -> AsyncIterator[SqlDashboardSnapshot]:
        try:
            async with self._sessions() as session:
                async with session.begin():
                    await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
                    await session.execute(text("SET LOCAL TIME ZONE 'UTC'"))
                    await session.execute(
                        text("SELECT set_config('statement_timeout',:timeout,true)"),
                        {"timeout": f"{self._statement_timeout_ms}ms"},
                    )
                    value = (await session.execute(text("SELECT transaction_timestamp()"))).scalar_one()
                    if not isinstance(value, datetime) or value.tzinfo is None:
                        raise DashboardActivityError("ANALYTICS_DATA_INTEGRITY_ERROR")
                    yield SqlDashboardSnapshot(session, value)
        except asyncio.CancelledError:
            raise
        except DashboardActivityError:
            raise
        except SQLAlchemyError as exc:
            raise DashboardActivityError("ANALYTICS_SOURCE_UNAVAILABLE") from exc


__all__ = [
    "ActivityPageRecord", "ActivityRecord", "CurrentRecord", "DashboardRepository",
    "DashboardSnapshotReader", "PeriodRecord", "ReviewRecord", "SqlDashboardRepository",
    "ValidationCatalogRow", "ValidationRecord", "ValidationRun",
]
