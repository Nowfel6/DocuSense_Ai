-- Dashboard Analytics and Activity query reference
-- Contract: database_production/workflows/02-specs/dashboard-activity-db-spec.md
-- Bind syntax is SQLAlchemy-style. Every query must run inside one READ ONLY,
-- REPEATABLE READ transaction using the authenticated company_id.

-- name: dashboard_status_snapshot
WITH status_counts AS (
    SELECT d.status, count(*)::bigint AS item_count
    FROM documents AS d
    WHERE d.company_id = CAST(:company_id AS uuid)
    GROUP BY d.status
), expected(status) AS (
    VALUES
      ('queued'), ('partitioning'), ('chunking'), ('vectorizing'),
      ('extracting'), ('pending_review'), ('approved'), ('rejected'), ('failed')
), distribution AS (
    SELECT e.status, COALESCE(s.item_count, 0)::bigint AS item_count
    FROM expected AS e
    LEFT JOIN status_counts AS s USING (status)
), export_count AS (
    SELECT count(*)::bigint AS active_export_jobs
    FROM export_jobs AS e
    WHERE e.company_id = CAST(:company_id AS uuid)
      AND e.mode = 'asynchronous'
      AND e.status IN ('queued', 'processing')
)
SELECT
    sum(item_count)::bigint AS total_documents,
    sum(item_count) FILTER (
      WHERE status IN ('queued','partitioning','chunking','vectorizing','extracting')
    )::bigint AS active_processing_documents,
    sum(item_count) FILTER (WHERE status = 'pending_review')::bigint AS pending_review_documents,
    sum(item_count) FILTER (WHERE status = 'approved')::bigint AS approved_documents,
    sum(item_count) FILTER (WHERE status = 'rejected')::bigint AS rejected_documents,
    sum(item_count) FILTER (WHERE status = 'failed')::bigint AS failed_documents,
    (SELECT active_export_jobs FROM export_count) AS active_export_jobs,
    jsonb_object_agg(status, item_count ORDER BY status) AS status_distribution
FROM distribution;

-- name: dashboard_period_metrics
WITH tenant_documents AS MATERIALIZED (
    SELECT d.id
    FROM documents AS d
    WHERE d.company_id = CAST(:company_id AS uuid)
), uploads AS (
    SELECT count(*)::bigint AS uploaded
    FROM documents AS d
    WHERE d.company_id = CAST(:company_id AS uuid)
      AND d.created_at >= CAST(:from_at AS timestamptz)
      AND d.created_at < CAST(:to_at AS timestamptz)
), job_metrics AS (
    SELECT
      count(*) FILTER (WHERE j.status = 'completed')::bigint AS processing_completed,
      count(*) FILTER (WHERE j.status = 'failed')::bigint AS processing_failed,
      count(*) FILTER (
        WHERE j.status = 'completed'
          AND j.started_at IS NOT NULL
          AND j.finished_at >= j.started_at
      )::bigint AS successful_processing_sample_count,
      count(*) FILTER (
        WHERE j.status = 'completed'
          AND (j.started_at IS NULL OR j.finished_at < j.started_at)
      )::bigint AS processing_duration_integrity_exclusion_count,
      round(avg(extract(epoch FROM (j.finished_at - j.started_at)) * 1000)
        FILTER (WHERE j.status = 'completed' AND j.started_at IS NOT NULL
                AND j.finished_at >= j.started_at))::bigint AS average_successful_processing_ms,
      round(percentile_cont(0.5) WITHIN GROUP (
        ORDER BY extract(epoch FROM (j.finished_at - j.started_at)) * 1000
      ) FILTER (WHERE j.status = 'completed' AND j.started_at IS NOT NULL
                AND j.finished_at >= j.started_at))::bigint AS median_successful_processing_ms
    FROM processing_jobs AS j
    JOIN tenant_documents AS d ON d.id = j.document_id
    WHERE j.status IN ('completed', 'failed')
      AND j.finished_at >= CAST(:from_at AS timestamptz)
      AND j.finished_at < CAST(:to_at AS timestamptz)
), review_metrics AS (
    SELECT
      count(*) FILTER (WHERE r.action = 'approved')::bigint AS review_approved,
      count(*) FILTER (WHERE r.action = 'rejected')::bigint AS review_rejected,
      count(*) FILTER (WHERE r.action = 'reopened')::bigint AS review_reopened
    FROM review_audit_events AS r
    JOIN tenant_documents AS d ON d.id = r.document_id
    WHERE r.action IN ('approved', 'rejected', 'reopened')
      AND r.created_at >= CAST(:from_at AS timestamptz)
      AND r.created_at < CAST(:to_at AS timestamptz)
), export_metrics AS (
    SELECT
      count(*) FILTER (
        WHERE e.completed_at >= CAST(:from_at AS timestamptz)
          AND e.completed_at < CAST(:to_at AS timestamptz)
      )::bigint AS export_completed,
      count(*) FILTER (
        WHERE e.failed_at >= CAST(:from_at AS timestamptz)
          AND e.failed_at < CAST(:to_at AS timestamptz)
      )::bigint AS export_failed
    FROM export_jobs AS e
    WHERE e.company_id = CAST(:company_id AS uuid)
)
SELECT * FROM uploads CROSS JOIN job_metrics CROSS JOIN review_metrics CROSS JOIN export_metrics;

-- name: dashboard_initial_validation
WITH catalog AS MATERIALIZED (
    SELECT c.pipeline_version, c.rule_id, c.scope_key, c.allows_not_applicable
    FROM jsonb_to_recordset(CAST(:validation_catalog_json AS jsonb)) AS c(
      pipeline_version text,
      rule_id text,
      scope_key text,
      allows_not_applicable boolean
    )
), candidate_runs AS MATERIALIZED (
    SELECT r.id, r.pipeline_version
    FROM extraction_runs AS r
    JOIN documents AS d ON d.id = r.document_id
    WHERE d.company_id = CAST(:company_id AS uuid)
      AND r.status = 'completed'
      AND r.finished_at >= CAST(:from_at AS timestamptz)
      AND r.finished_at < CAST(:to_at AS timestamptz)
), catalog_sizes AS MATERIALIZED (
    SELECT pipeline_version, count(*)::integer AS required_count
    FROM catalog
    GROUP BY pipeline_version
), evaluated AS (
    SELECT
      r.id,
      COALESCE(s.required_count, 0)::integer AS required_count,
      count(v.id) FILTER (WHERE c.rule_id IS NOT NULL)::integer AS matched_count,
      count(v.id) FILTER (
        WHERE c.rule_id IS NOT NULL
          AND (v.status = 'passed'
            OR (v.status = 'not_applicable' AND c.allows_not_applicable))
      )::integer AS passing_count,
      count(v.id) FILTER (WHERE c.rule_id IS NULL)::integer AS unexpected_count
    FROM candidate_runs AS r
    LEFT JOIN catalog_sizes AS s ON s.pipeline_version = r.pipeline_version
    LEFT JOIN validation_results AS v ON v.extraction_run_id = r.id
    LEFT JOIN catalog AS c
      ON c.pipeline_version = r.pipeline_version
     AND c.rule_id = v.rule_id
     AND c.scope_key = v.scope_key
    GROUP BY r.id, s.required_count
), failed_runs AS (
    SELECT count(*)::bigint AS failed_run_count
    FROM extraction_runs AS r
    JOIN documents AS d ON d.id = r.document_id
    WHERE d.company_id = CAST(:company_id AS uuid)
      AND r.status = 'failed'
      AND r.finished_at >= CAST(:from_at AS timestamptz)
      AND r.finished_at < CAST(:to_at AS timestamptz)
)
SELECT
  count(*) FILTER (
    WHERE required_count > 0 AND matched_count = required_count
      AND passing_count = required_count AND unexpected_count = 0
  )::bigint AS passed_count,
  count(*) FILTER (
    WHERE required_count > 0 AND matched_count = required_count
      AND unexpected_count = 0
  )::bigint AS eligible_count,
  count(*) FILTER (
    WHERE required_count > 0
      AND (matched_count <> required_count OR unexpected_count <> 0)
  )::bigint AS incomplete_count,
  count(*) FILTER (WHERE required_count = 0)::bigint AS unknown_catalog_count,
  round(
    100.0 * count(*) FILTER (
      WHERE required_count > 0 AND matched_count = required_count
        AND passing_count = required_count AND unexpected_count = 0
    ) / NULLIF(count(*) FILTER (
      WHERE required_count > 0 AND matched_count = required_count
        AND unexpected_count = 0
    ), 0), 2
  ) AS initial_validation_pass_rate,
  (SELECT failed_run_count FROM failed_runs) AS failed_run_count
FROM evaluated;

-- name: dashboard_review_cycle_metrics
WITH tenant_documents AS MATERIALIZED (
    SELECT d.id
    FROM documents AS d
    WHERE d.company_id = CAST(:company_id AS uuid)
), initial_success AS MATERIALIZED (
    SELECT j.document_id, j.finished_at
    FROM processing_jobs AS j
    JOIN tenant_documents AS d ON d.id = j.document_id
    WHERE j.status = 'completed'
), all_terminal_events AS MATERIALIZED (
    SELECT r.id, r.document_id, r.action, r.review_revision, r.created_at
    FROM review_audit_events AS r
    JOIN tenant_documents AS d ON d.id = r.document_id
    WHERE r.action IN ('approved', 'rejected')
), terminal_events AS MATERIALIZED (
    SELECT r.id, r.document_id, r.action, r.review_revision, r.created_at,
      COALESCE((
        SELECT max(x.review_revision)
        FROM review_audit_events AS x
        WHERE x.document_id = r.document_id
          AND x.action = 'reopened'
          AND (x.review_revision, x.created_at, x.id)
              < (r.review_revision, r.created_at, r.id)
      ), 0)::bigint AS lower_revision
    FROM all_terminal_events AS r
    WHERE r.created_at >= CAST(:from_at AS timestamptz)
      AND r.created_at < CAST(:to_at AS timestamptz)
), cycle_facts AS (
    SELECT t.*,
      EXISTS (
        SELECT 1
        FROM review_audit_changes AS c
        JOIN review_audit_events AS e ON e.id = c.audit_event_id
        WHERE e.document_id = t.document_id
          AND e.review_revision > t.lower_revision
          AND e.review_revision <= t.review_revision
      ) AS corrected
    FROM terminal_events AS t
), first_decisions AS (
    SELECT DISTINCT ON (t.document_id)
      t.document_id, t.created_at AS decision_at, s.finished_at
    FROM all_terminal_events AS t
    LEFT JOIN initial_success AS s ON s.document_id = t.document_id
    ORDER BY t.document_id, t.review_revision, t.created_at, t.id
)
SELECT
  count(*) FILTER (WHERE c.action = 'approved')::bigint AS approval_cycle_count,
  count(*) FILTER (WHERE c.action = 'approved' AND c.corrected)::bigint AS corrected_approval_cycle_count,
  round(100.0 * count(*) FILTER (WHERE c.action = 'approved' AND c.corrected)
    / NULLIF(count(*) FILTER (WHERE c.action = 'approved'), 0), 2) AS review_correction_rate,
  (SELECT count(*) FROM first_decisions f
    WHERE f.decision_at >= CAST(:from_at AS timestamptz)
      AND f.decision_at < CAST(:to_at AS timestamptz)
      AND f.finished_at IS NOT NULL AND f.decision_at >= f.finished_at
  )::bigint AS first_decision_sample_count,
  (SELECT round(avg(extract(epoch FROM (f.decision_at - f.finished_at)) * 1000))::bigint
    FROM first_decisions f
    WHERE f.decision_at >= CAST(:from_at AS timestamptz)
      AND f.decision_at < CAST(:to_at AS timestamptz)
      AND f.finished_at IS NOT NULL AND f.decision_at >= f.finished_at
  ) AS average_time_to_first_decision_ms,
  (SELECT count(*) FROM first_decisions f
    WHERE f.decision_at >= CAST(:from_at AS timestamptz)
      AND f.decision_at < CAST(:to_at AS timestamptz)
      AND (f.finished_at IS NULL OR f.decision_at < f.finished_at)
  )::bigint AS review_timing_integrity_exclusion_count
FROM cycle_facts AS c;

-- name: dashboard_review_backlog_series
WITH parameters AS (
  SELECT CAST(:company_id AS uuid) AS company_id,
         CAST(:from_at AS timestamptz) AS from_at,
         CAST(:to_at AS timestamptz) AS to_at,
         CAST(:bucket AS text) AS bucket
), event_stream AS MATERIALIZED (
  SELECT j.finished_at AS occurred_at, 1::bigint AS delta
  FROM processing_jobs AS j
  JOIN documents AS d ON d.id = j.document_id
  JOIN parameters AS p ON p.company_id = d.company_id
  WHERE j.status = 'completed' AND j.finished_at < p.to_at
  UNION ALL
  SELECT r.created_at,
         CASE WHEN r.action = 'reopened' THEN 1::bigint ELSE -1::bigint END
  FROM review_audit_events AS r
  JOIN documents AS d ON d.id = r.document_id
  JOIN parameters AS p ON p.company_id = d.company_id
  WHERE r.action IN ('approved','rejected','reopened') AND r.created_at < p.to_at
), opening AS (
  SELECT COALESCE(sum(e.delta) FILTER (WHERE e.occurred_at < p.from_at), 0)::bigint AS balance
  FROM event_stream AS e CROSS JOIN parameters AS p
), bucketed AS (
  SELECT CASE p.bucket
      WHEN 'day' THEN date_trunc('day', e.occurred_at)
      WHEN 'week' THEN date_trunc('week', e.occurred_at)
      WHEN 'month' THEN date_trunc('month', e.occurred_at)
    END AS bucket_start,
    sum(e.delta)::bigint AS delta
  FROM event_stream AS e CROSS JOIN parameters AS p
  WHERE e.occurred_at >= p.from_at AND e.occurred_at < p.to_at
  GROUP BY 1
), event_time_deltas AS (
  SELECT occurred_at, sum(delta)::bigint AS delta
  FROM event_stream
  GROUP BY occurred_at
), integrity AS (
  SELECT COALESCE(min(balance), 0) < 0 AS has_integrity_failure
  FROM (
    SELECT sum(delta) OVER (ORDER BY occurred_at ROWS UNBOUNDED PRECEDING) AS balance
    FROM event_time_deltas
  ) AS running
), spine AS (
  SELECT generate_series(
    CASE p.bucket
      WHEN 'day' THEN date_trunc('day', p.from_at)
      WHEN 'week' THEN date_trunc('week', p.from_at)
      WHEN 'month' THEN date_trunc('month', p.from_at)
    END,
    CASE p.bucket
      WHEN 'day' THEN date_trunc('day', p.to_at - interval '1 microsecond')
      WHEN 'week' THEN date_trunc('week', p.to_at - interval '1 microsecond')
      WHEN 'month' THEN date_trunc('month', p.to_at - interval '1 microsecond')
    END,
    CASE p.bucket WHEN 'day' THEN interval '1 day'
                  WHEN 'week' THEN interval '1 week'
                  WHEN 'month' THEN interval '1 month' END
  ) AS bucket_start,
  p.bucket, p.from_at, p.to_at
  FROM parameters AS p
), balances AS (
  SELECT s.bucket_start,
    o.balance + sum(COALESCE(b.delta, 0)) OVER (
      ORDER BY s.bucket_start ROWS UNBOUNDED PRECEDING
    ) AS review_backlog_end_of_bucket
  FROM spine AS s
  CROSS JOIN opening AS o
  LEFT JOIN bucketed AS b USING (bucket_start)
)
SELECT bucket_start, COALESCE(review_backlog_end_of_bucket, 0)::bigint AS review_backlog_end_of_bucket,
       i.has_integrity_failure
FROM balances CROSS JOIN integrity AS i
ORDER BY bucket_start;

-- name: activity_admin_operator_page
WITH activity AS (
  SELECT d.id AS source_uuid, 'document_uploaded'::text AS event_type,
    d.created_at AS occurred_at, 'document'::text AS subject_type,
    d.id AS document_id, NULL::uuid AS export_id, d.uploaded_by AS actor_user_id,
    left(d.file_name, 255) AS display_label, 'document.uploaded'::text AS summary_code
  FROM documents AS d WHERE d.company_id = CAST(:company_id AS uuid)
  UNION ALL
  SELECT j.id, CASE j.status WHEN 'completed' THEN 'processing_completed' ELSE 'processing_failed' END,
    j.finished_at, 'document', d.id, NULL::uuid, NULL::uuid,
    left(d.file_name,255), CASE j.status WHEN 'completed' THEN 'processing.completed' ELSE 'processing.failed' END
  FROM processing_jobs AS j JOIN documents AS d ON d.id = j.document_id
  WHERE d.company_id = CAST(:company_id AS uuid) AND j.status IN ('completed','failed')
  UNION ALL
  SELECT r.id,
    CASE r.action WHEN 'field_edited' THEN 'review_saved' WHEN 'approved' THEN 'document_approved'
      WHEN 'rejected' THEN 'document_rejected' WHEN 'reopened' THEN 'document_reopened' END,
    r.created_at, 'document', d.id, NULL::uuid, r.actor_user_id,
    left(d.file_name,255), 'review.' || r.action
  FROM review_audit_events AS r JOIN documents AS d ON d.id = r.document_id
  WHERE d.company_id = CAST(:company_id AS uuid)
    AND r.action IN ('field_edited','approved','rejected','reopened')
  UNION ALL
  SELECT e.id, x.event_type, x.occurred_at, 'export', NULL::uuid, e.id,
    e.requested_by_user_id, 'Export'::text, 'export.' || x.summary_suffix
  FROM export_jobs AS e
  CROSS JOIN LATERAL (VALUES
    ('export_requested'::text, e.created_at, 'requested'::text),
    ('export_completed', e.completed_at, 'completed'),
    ('export_failed', e.failed_at, 'failed'),
    ('export_expired', e.expired_at, 'expired')
  ) AS x(event_type, occurred_at, summary_suffix)
  WHERE e.company_id = CAST(:company_id AS uuid) AND x.occurred_at IS NOT NULL
), visible AS (
  SELECT *, event_type || ':' || source_uuid::text AS event_id
  FROM activity
  WHERE occurred_at <= CAST(:snapshot_at AS timestamptz)
    AND (CAST(:event_types_json AS jsonb) = '[]'::jsonb
      OR event_type IN (SELECT jsonb_array_elements_text(CAST(:event_types_json AS jsonb))))
)
SELECT event_id, event_type, occurred_at, subject_type, document_id, export_id,
       actor_user_id, display_label, summary_code, count(*) OVER ()::bigint AS total_count
FROM visible
ORDER BY occurred_at DESC, event_type ASC, source_uuid DESC
LIMIT CAST(:page_size AS integer)
OFFSET (CAST(:page AS integer) - 1) * CAST(:page_size AS integer);

-- name: activity_viewer_page
WITH viewer_activity AS (
  SELECT r.id AS source_uuid, 'document_approved'::text AS event_type,
    r.created_at AS occurred_at, 'document'::text AS subject_type,
    d.id AS document_id, r.actor_user_id,
    left(d.file_name,255) AS display_label, 'review.approved'::text AS summary_code
  FROM review_audit_events AS r
  JOIN documents AS d ON d.id = r.document_id
  WHERE d.company_id = CAST(:company_id AS uuid)
    AND d.status = 'approved' AND r.action = 'approved'
  UNION ALL
  SELECT e.id, 'export_completed', e.completed_at, 'export', NULL::uuid,
    NULL::uuid, 'Export completed', 'export.completed'
  FROM export_jobs AS e
  WHERE e.company_id = CAST(:company_id AS uuid) AND e.completed_at IS NOT NULL
), visible AS (
  SELECT *, CASE event_type
    WHEN 'export_completed' THEN 'export_completed:opaque_' || encode(digest(
      convert_to('docusense-activity-viewer-v1', 'UTF8') || decode('00','hex') ||
      convert_to(CAST(:company_id AS uuid)::text, 'UTF8') || decode('00','hex') ||
      convert_to('export_completed', 'UTF8') || decode('00','hex') ||
      convert_to(source_uuid::text, 'UTF8'), 'sha256'), 'hex')
    ELSE event_type || ':' || source_uuid::text END AS event_id
  FROM viewer_activity
  WHERE occurred_at <= CAST(:snapshot_at AS timestamptz)
    AND (CAST(:event_types_json AS jsonb) = '[]'::jsonb
      OR event_type IN (SELECT jsonb_array_elements_text(CAST(:event_types_json AS jsonb))))
)
SELECT event_id, event_type, occurred_at, subject_type, document_id,
       NULL::uuid AS export_id, actor_user_id, display_label, summary_code,
       count(*) OVER ()::bigint AS total_count
FROM visible
ORDER BY occurred_at DESC, event_type ASC, source_uuid DESC
LIMIT CAST(:page_size AS integer)
OFFSET (CAST(:page AS integer) - 1) * CAST(:page_size AS integer);
