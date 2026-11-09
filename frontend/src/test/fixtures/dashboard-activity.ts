import type { ActivityEnvelope, DashboardEnvelope } from "@/features/dashboard-activity/types";

export const documentId = "11111111-1111-4111-8111-111111111111";
export const actorId = "22222222-2222-4222-8222-222222222222";

export function dashboardEnvelope(): DashboardEnvelope {
  const buckets = ["2026-08-17T00:00:00Z", "2026-08-18T00:00:00Z"];
  return {
    success: true,
    message: "Dashboard analytics loaded.",
    meta: { timestamp: "2026-08-18T12:00:00Z", request_id: "req_dashboard" },
    data: {
      definition_version: "dashboard-metrics-v1",
      period: { from: "2026-08-17T00:00:00Z", to: "2026-08-19T00:00:00Z", bucket: "day", snapshot_at: "2026-08-19T00:00:00Z" },
      current: { total_documents: 10, active_processing_documents: 3, pending_review_documents: 2, approved_documents: 3, failed_documents: 1, active_export_jobs: 1 },
      period_metrics: {
        documents_uploaded: 4, processing_completed: 3, processing_failed: 1, approval_events: 2, rejection_events: 1, reopen_events: 1, exports_completed: 2, exports_failed: 1,
        average_successful_processing_ms: 2500, median_successful_processing_ms: 2200, successful_processing_sample_count: 3, processing_duration_integrity_exclusion_count: 1,
        initial_validation_pass_rate: "66.67", initial_validation_passed_run_count: 2, initial_validation_eligible_run_count: 3, initial_validation_incomplete_rule_set_count: 1, initial_validation_unknown_catalog_count: 0, failed_extraction_run_count: 1,
        review_decision_count: 3, reviewed_document_count: 3, approved_cycle_count: 2, corrected_approval_count: 1, review_correction_rate: "50.00",
        average_time_to_first_decision_ms: 3600000, first_decision_sample_count: 2, review_timing_integrity_exclusion_count: 1,
      },
      status_distribution: [
        { status: "queued", count: 1 }, { status: "partitioning", count: 1 }, { status: "chunking", count: 1 }, { status: "vectorizing", count: 0 }, { status: "extracting", count: 0 },
        { status: "pending_review", count: 2 }, { status: "approved", count: 3 }, { status: "rejected", count: 1 }, { status: "failed", count: 1 },
      ],
      trends: {
        document_volume: buckets.map((bucket_start, index) => ({ bucket_start, uploaded: index + 1, processing_completed: 1, processing_failed: index })),
        review_decisions: buckets.map((bucket_start, index) => ({ bucket_start, approved: 1, rejected: index, reopened: index })),
        export_outcomes: buckets.map((bucket_start, index) => ({ bucket_start, completed: 1, failed: index })),
        successful_processing_duration: buckets.map((bucket_start, index) => ({ bucket_start, average_ms: 2000 + index * 500, median_ms: 1800 + index * 400, sample_count: 1 + index, integrity_exclusion_count: index })),
        review_backlog_end_of_bucket: buckets.map((bucket_start, index) => ({ bucket_start, review_backlog_end_of_bucket: 2 + index })),
      },
      source_status: { auth: "available", ingestion: "available", processing: "available", review: "available", export: "available" },
    },
  };
}

export function activityEnvelope(role: "admin" | "operator" | "viewer" = "admin"): ActivityEnvelope {
  const viewer = role === "viewer";
  return {
    success: true,
    message: "Recent activity loaded.",
    meta: { timestamp: "2026-08-18T12:00:00Z", request_id: "req_activity" },
    data: {
      snapshot_at: "2026-08-18T12:00:00Z",
      items: [{
        event_id: `document_approved:${documentId}`,
        event_type: "document_approved",
        occurred_at: "2026-08-18T11:30:00Z",
        subject_type: "document",
        document_id: documentId,
        export_id: null,
        actor_user_id: role === "admin" ? actorId : null,
        actor_display_name: viewer ? null : "Alex Reviewer",
        display_label: "Invoice ACME-1042",
        summary_code: "review.approved",
        link: `/documents/${documentId}`,
      }],
    },
    pagination: { page: 1, page_size: 20, total_records: 1, total_pages: 1, has_next: false, has_prev: false },
  };
}

