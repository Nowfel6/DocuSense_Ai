import type { UserRole } from "@/lib/auth/session-types";

export type DashboardBucket = "day" | "week" | "month";
export type DashboardRole = UserRole;
export type DocumentStatus = "queued" | "partitioning" | "chunking" | "vectorizing" | "extracting" | "pending_review" | "approved" | "rejected" | "failed";
export type ActivityEventType = "document_uploaded" | "processing_completed" | "processing_failed" | "review_saved" | "document_approved" | "document_rejected" | "document_reopened" | "export_requested" | "export_completed" | "export_failed" | "export_expired";
export type ActivitySummaryCode = "document.uploaded" | "processing.completed" | "processing.failed" | "review.field_edited" | "review.approved" | "review.rejected" | "review.reopened" | "export.requested" | "export.completed" | "export.failed" | "export.expired";

export interface DashboardQuery {
  from?: string;
  to?: string;
  bucket: DashboardBucket;
}

export interface DashboardUrlState {
  query: DashboardQuery;
  error?: string;
}

export interface DashboardPeriod {
  from: string;
  to: string;
  bucket: DashboardBucket;
  snapshot_at: string;
}

export interface CurrentDashboardMetrics {
  total_documents: number;
  active_processing_documents: number;
  pending_review_documents: number;
  approved_documents: number;
  failed_documents: number;
  active_export_jobs: number;
}

export interface PeriodDashboardMetrics {
  documents_uploaded: number;
  processing_completed: number;
  processing_failed: number;
  approval_events: number;
  rejection_events: number;
  reopen_events: number;
  exports_completed: number;
  exports_failed: number;
  average_successful_processing_ms: number | null;
  median_successful_processing_ms: number | null;
  successful_processing_sample_count: number;
  processing_duration_integrity_exclusion_count: number;
  initial_validation_pass_rate: string | null;
  initial_validation_passed_run_count: number;
  initial_validation_eligible_run_count: number;
  initial_validation_incomplete_rule_set_count: number;
  initial_validation_unknown_catalog_count: number;
  failed_extraction_run_count: number;
  review_decision_count: number;
  reviewed_document_count: number;
  approved_cycle_count: number;
  corrected_approval_count: number;
  review_correction_rate: string | null;
  average_time_to_first_decision_ms: number | null;
  first_decision_sample_count: number;
  review_timing_integrity_exclusion_count: number;
}

export interface StatusDistributionPoint { status: DocumentStatus; count: number }
export interface DocumentVolumePoint { bucket_start: string; uploaded: number; processing_completed: number; processing_failed: number }
export interface ReviewDecisionPoint { bucket_start: string; approved: number; rejected: number; reopened: number }
export interface ExportOutcomePoint { bucket_start: string; completed: number; failed: number }
export interface ProcessingDurationPoint { bucket_start: string; average_ms: number | null; median_ms: number | null; sample_count: number; integrity_exclusion_count: number }
export interface ReviewBacklogPoint { bucket_start: string; review_backlog_end_of_bucket: number }

export interface DashboardData {
  definition_version: "dashboard-metrics-v1";
  period: DashboardPeriod;
  current: CurrentDashboardMetrics;
  period_metrics: PeriodDashboardMetrics;
  status_distribution: StatusDistributionPoint[];
  trends: {
    document_volume: DocumentVolumePoint[];
    review_decisions: ReviewDecisionPoint[];
    export_outcomes: ExportOutcomePoint[];
    successful_processing_duration: ProcessingDurationPoint[];
    review_backlog_end_of_bucket: ReviewBacklogPoint[];
  };
  source_status: { auth: "available"; ingestion: "available"; processing: "available"; review: "available"; export: "available" };
}

export interface ApiMeta { timestamp: string; request_id: string }
export interface DashboardEnvelope { success: true; data: DashboardData; message: string; meta: ApiMeta }

export interface ActivityItem {
  event_id: string;
  event_type: ActivityEventType;
  occurred_at: string;
  subject_type: "document" | "export";
  document_id: string | null;
  export_id: string | null;
  actor_user_id: string | null;
  actor_display_name: string | null;
  display_label: string;
  summary_code: ActivitySummaryCode;
  link: string | null;
}

export interface Pagination {
  page: number;
  page_size: number;
  total_records: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface ActivityEnvelope {
  success: true;
  data: { snapshot_at: string; items: ActivityItem[] };
  message: string;
  meta: ApiMeta;
  pagination: Pagination;
}

export interface ReportDraft {
  mode: "default" | "custom";
  from: string;
  to: string;
  bucket: DashboardBucket;
}

export type ReportErrors = Partial<Record<"from" | "to" | "range", string>>;

export interface DashboardActivityViewProps {
  role: DashboardRole;
  initialState: DashboardUrlState;
}

export const DOCUMENT_STATUSES: readonly DocumentStatus[] = ["queued", "partitioning", "chunking", "vectorizing", "extracting", "pending_review", "approved", "rejected", "failed"];
export const ACTIVITY_EVENT_TYPES: readonly ActivityEventType[] = ["document_uploaded", "processing_completed", "processing_failed", "review_saved", "document_approved", "document_rejected", "document_reopened", "export_requested", "export_completed", "export_failed", "export_expired"];

