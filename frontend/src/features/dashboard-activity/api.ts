import { apiEnvelopeRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

import {
  ACTIVITY_EVENT_TYPES,
  DOCUMENT_STATUSES,
  type ActivityEnvelope,
  type ActivityEventType,
  type ActivityItem,
  type ActivitySummaryCode,
  type DashboardActivityViewProps,
  type DashboardBucket,
  type DashboardData,
  type DashboardEnvelope,
  type DashboardQuery,
  type DashboardRole,
  type DashboardUrlState,
  type Pagination,
  type PeriodDashboardMetrics,
  type ReportDraft,
  type ReportErrors,
} from "./types";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const RATE = /^(?:\d{1,2}|100)\.\d{2}$/;
const LOCAL_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;
const CONTROL = /[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]/;
const BUCKETS = new Set<DashboardBucket>(["day", "week", "month"]);
const EVENT_TYPES = new Set<string>(ACTIVITY_EVENT_TYPES);

const EVENT_SHAPES: Record<ActivityEventType, ["document" | "export", ActivitySummaryCode]> = {
  document_uploaded: ["document", "document.uploaded"],
  processing_completed: ["document", "processing.completed"],
  processing_failed: ["document", "processing.failed"],
  review_saved: ["document", "review.field_edited"],
  document_approved: ["document", "review.approved"],
  document_rejected: ["document", "review.rejected"],
  document_reopened: ["document", "review.reopened"],
  export_requested: ["export", "export.requested"],
  export_completed: ["export", "export.completed"],
  export_failed: ["export", "export.failed"],
  export_expired: ["export", "export.expired"],
};

function invalid(): never {
  throw new ApiError("The service returned an unexpected response.", { code: "INVALID_API_RESPONSE" });
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid();
  return value as Record<string, unknown>;
}

function exact(value: Record<string, unknown>, keys: readonly string[]) {
  const actual = Object.keys(value);
  if (actual.length !== keys.length || actual.some((key) => !keys.includes(key))) invalid();
}

function integer(value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= min && value <= max;
}

function utc(value: unknown): value is string {
  return typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && !Number.isNaN(Date.parse(value));
}

function plain(value: unknown, max: number): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= max && !CONTROL.test(value);
}

function nullableUuid(value: unknown): value is string | null {
  return value === null || typeof value === "string" && UUID.test(value);
}

function meta(value: unknown) {
  const item = record(value);
  exact(item, ["timestamp", "request_id"]);
  if (!utc(item.timestamp) || !plain(item.request_id, 128)) invalid();
  return item as unknown as DashboardEnvelope["meta"];
}

function nonnegativeFields(value: unknown, keys: readonly string[]): Record<string, number> {
  const item = record(value);
  exact(item, keys);
  if (keys.some((key) => !integer(item[key]))) invalid();
  return item as Record<string, number>;
}

const PERIOD_KEYS = [
  "documents_uploaded", "processing_completed", "processing_failed", "approval_events", "rejection_events", "reopen_events", "exports_completed", "exports_failed",
  "average_successful_processing_ms", "median_successful_processing_ms", "successful_processing_sample_count", "processing_duration_integrity_exclusion_count",
  "initial_validation_pass_rate", "initial_validation_passed_run_count", "initial_validation_eligible_run_count", "initial_validation_incomplete_rule_set_count", "initial_validation_unknown_catalog_count", "failed_extraction_run_count",
  "review_decision_count", "reviewed_document_count", "approved_cycle_count", "corrected_approval_count", "review_correction_rate", "average_time_to_first_decision_ms", "first_decision_sample_count", "review_timing_integrity_exclusion_count",
] as const;

function periodMetrics(value: unknown): PeriodDashboardMetrics {
  const item = record(value);
  exact(item, PERIOD_KEYS);
  const nullableDurations = ["average_successful_processing_ms", "median_successful_processing_ms", "average_time_to_first_decision_ms"] as const;
  const rates = ["initial_validation_pass_rate", "review_correction_rate"] as const;
  for (const key of PERIOD_KEYS) {
    if (nullableDurations.includes(key as typeof nullableDurations[number])) {
      if (item[key] !== null && !integer(item[key])) invalid();
    } else if (rates.includes(key as typeof rates[number])) {
      if (item[key] !== null && !(typeof item[key] === "string" && RATE.test(item[key]) && Number(item[key]) <= 100)) invalid();
    } else if (!integer(item[key])) invalid();
  }
  if (item.review_decision_count !== (item.approval_events as number) + (item.rejection_events as number)) invalid();
  if ((item.initial_validation_passed_run_count as number) > (item.initial_validation_eligible_run_count as number)) invalid();
  if ((item.corrected_approval_count as number) > (item.approved_cycle_count as number)) invalid();
  if ((item.initial_validation_pass_rate === null) !== (item.initial_validation_eligible_run_count === 0)) invalid();
  if ((item.review_correction_rate === null) !== (item.approved_cycle_count === 0)) invalid();
  const processingEmpty = item.successful_processing_sample_count === 0;
  if ((item.average_successful_processing_ms === null) !== processingEmpty || (item.median_successful_processing_ms === null) !== processingEmpty) invalid();
  if ((item.average_time_to_first_decision_ms === null) !== (item.first_decision_sample_count === 0)) invalid();
  return item as unknown as PeriodDashboardMetrics;
}

function pointArray<T>(value: unknown, keys: readonly string[], nullable: readonly string[] = []): T[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 366) invalid();
  return value.map((entry) => {
    const item = record(entry);
    exact(item, ["bucket_start", ...keys]);
    if (!utc(item.bucket_start)) invalid();
    for (const key of keys) {
      if (nullable.includes(key) ? item[key] !== null && !integer(item[key]) : !integer(item[key])) invalid();
    }
    return item as T;
  });
}

function dashboardData(value: unknown): DashboardData {
  const item = record(value);
  exact(item, ["definition_version", "period", "current", "period_metrics", "status_distribution", "trends", "source_status"]);
  if (item.definition_version !== "dashboard-metrics-v1") invalid();
  const period = record(item.period);
  exact(period, ["from", "to", "bucket", "snapshot_at"]);
  if (!utc(period.from) || !utc(period.to) || !utc(period.snapshot_at) || !BUCKETS.has(period.bucket as DashboardBucket) || Date.parse(period.from) >= Date.parse(period.to) || Date.parse(period.to) > Date.parse(period.snapshot_at)) invalid();
  const currentKeys = ["total_documents", "active_processing_documents", "pending_review_documents", "approved_documents", "failed_documents", "active_export_jobs"] as const;
  const current = nonnegativeFields(item.current, currentKeys);
  const metrics = periodMetrics(item.period_metrics);
  if (!Array.isArray(item.status_distribution) || item.status_distribution.length !== DOCUMENT_STATUSES.length) invalid();
  const distribution = item.status_distribution.map((entry, index) => {
    const point = record(entry);
    exact(point, ["status", "count"]);
    if (point.status !== DOCUMENT_STATUSES[index] || !integer(point.count)) invalid();
    return point as unknown as DashboardData["status_distribution"][number];
  });
  if (distribution.reduce((sum, point) => sum + point.count, 0) !== current.total_documents) invalid();
  if (distribution.slice(0, 5).reduce((sum, point) => sum + point.count, 0) !== current.active_processing_documents) invalid();
  const trends = record(item.trends);
  exact(trends, ["document_volume", "review_decisions", "export_outcomes", "successful_processing_duration", "review_backlog_end_of_bucket"]);
  const documentVolume = pointArray<DashboardData["trends"]["document_volume"][number]>(trends.document_volume, ["uploaded", "processing_completed", "processing_failed"]);
  const reviewDecisions = pointArray<DashboardData["trends"]["review_decisions"][number]>(trends.review_decisions, ["approved", "rejected", "reopened"]);
  const exportOutcomes = pointArray<DashboardData["trends"]["export_outcomes"][number]>(trends.export_outcomes, ["completed", "failed"]);
  const durations = pointArray<DashboardData["trends"]["successful_processing_duration"][number]>(trends.successful_processing_duration, ["average_ms", "median_ms", "sample_count", "integrity_exclusion_count"], ["average_ms", "median_ms"]);
  durations.forEach((point) => {
    if ((point.average_ms === null) !== (point.sample_count === 0) || (point.median_ms === null) !== (point.sample_count === 0)) invalid();
  });
  const backlog = pointArray<DashboardData["trends"]["review_backlog_end_of_bucket"][number]>(trends.review_backlog_end_of_bucket, ["review_backlog_end_of_bucket"]);
  const spines = [documentVolume, reviewDecisions, exportOutcomes, durations, backlog].map((series) => series.map((point) => point.bucket_start));
  if (spines.some((spine) => spine.length !== spines[0].length || spine.some((stamp, index) => stamp !== spines[0][index]))) invalid();
  if (spines[0].some((stamp, index) => index > 0 && Date.parse(stamp) <= Date.parse(spines[0][index - 1]))) invalid();
  const sources = record(item.source_status);
  exact(sources, ["auth", "ingestion", "processing", "review", "export"]);
  if (Object.values(sources).some((status) => status !== "available")) invalid();
  return {
    definition_version: "dashboard-metrics-v1",
    period: period as unknown as DashboardData["period"],
    current: current as unknown as DashboardData["current"],
    period_metrics: metrics,
    status_distribution: distribution,
    trends: { document_volume: documentVolume, review_decisions: reviewDecisions, export_outcomes: exportOutcomes, successful_processing_duration: durations, review_backlog_end_of_bucket: backlog },
    source_status: sources as unknown as DashboardData["source_status"],
  };
}

export function validateDashboardEnvelope(value: unknown): DashboardEnvelope {
  const envelope = record(value);
  exact(envelope, ["success", "data", "message", "meta"]);
  if (envelope.success !== true || !plain(envelope.message, 300)) invalid();
  return { success: true, data: dashboardData(envelope.data), message: envelope.message, meta: meta(envelope.meta) };
}

function pagination(value: unknown): Pagination {
  const item = record(value);
  exact(item, ["page", "page_size", "total_records", "total_pages", "has_next", "has_prev"]);
  if (!integer(item.page, 1) || !integer(item.page_size, 1, 100) || !integer(item.total_records) || !integer(item.total_pages) || typeof item.has_next !== "boolean" || typeof item.has_prev !== "boolean") invalid();
  if (item.has_prev !== ((item.page as number) > 1) || item.has_next !== ((item.page as number) < (item.total_pages as number))) invalid();
  return item as unknown as Pagination;
}

function activityItem(value: unknown, role: DashboardRole): ActivityItem {
  const item = record(value);
  exact(item, ["event_id", "event_type", "occurred_at", "subject_type", "document_id", "export_id", "actor_user_id", "actor_display_name", "display_label", "summary_code", "link"]);
  if (!plain(item.event_id, 128) || !EVENT_TYPES.has(item.event_type as string) || !utc(item.occurred_at) || !nullableUuid(item.document_id) || !nullableUuid(item.export_id) || !nullableUuid(item.actor_user_id)
    || !(item.actor_display_name === null || plain(item.actor_display_name, 100)) || !plain(item.display_label, 255) || !(item.link === null || plain(item.link, 500))) invalid();
  const shape = EVENT_SHAPES[item.event_type as ActivityEventType];
  if (item.subject_type !== shape[0] || item.summary_code !== shape[1]) invalid();
  if (item.subject_type === "document" ? item.document_id === null || item.export_id !== null : item.document_id !== null) invalid();
  if (item.link !== null && (item.document_id === null || item.link !== `/documents/${item.document_id}`)) invalid();
  if (role === "viewer" && (!new Set(["document_approved", "export_completed"]).has(item.event_type as string) || item.actor_user_id !== null || item.actor_display_name !== null || item.export_id !== null)) invalid();
  if (role === "viewer" && item.event_type === "export_completed" && item.link !== null) invalid();
  if (role === "operator" && item.actor_user_id !== null) invalid();
  return item as unknown as ActivityItem;
}

export function validateActivityEnvelope(value: unknown, role: DashboardRole): ActivityEnvelope {
  const envelope = record(value);
  exact(envelope, ["success", "data", "message", "meta", "pagination"]);
  if (envelope.success !== true || !plain(envelope.message, 300)) invalid();
  const data = record(envelope.data);
  exact(data, ["snapshot_at", "items"]);
  if (!utc(data.snapshot_at) || !Array.isArray(data.items)) invalid();
  const page = pagination(envelope.pagination);
  const items = data.items.map((entry) => activityItem(entry, role));
  if (items.length > page.page_size || new Set(items.map((item) => item.event_id)).size !== items.length || items.some((item) => Date.parse(item.occurred_at) > Date.parse(data.snapshot_at as string))) invalid();
  return { success: true, data: { snapshot_at: data.snapshot_at, items }, message: envelope.message, meta: meta(envelope.meta), pagination: page };
}

export function parseDashboardUrl(params: URLSearchParams): DashboardUrlState {
  const allowed = new Set(["from", "to", "bucket"]);
  if ([...params.keys()].some((key) => !allowed.has(key)) || [...allowed].some((key) => params.getAll(key).length > 1)) return { query: { bucket: "day" }, error: "The dashboard URL contained unsupported report options and was reset." };
  const from = params.get("from");
  const to = params.get("to");
  const bucket = params.get("bucket") ?? "day";
  if (!BUCKETS.has(bucket as DashboardBucket) || Boolean(from) !== Boolean(to) || from && !utc(from) || to && !utc(to) || from && to && Date.parse(from) >= Date.parse(to)) return { query: { bucket: "day" }, error: "The dashboard URL contained an invalid report range and was reset." };
  return { query: { ...(from && to ? { from: new Date(from).toISOString(), to: new Date(to).toISOString() } : {}), bucket: bucket as DashboardBucket } };
}

export function draftFromQuery(query: DashboardQuery): ReportDraft {
  const local = (value?: string) => value ? new Date(value).toISOString().slice(0, 16) : "";
  return { mode: query.from && query.to ? "custom" : "default", from: local(query.from), to: local(query.to), bucket: query.bucket };
}

export function serializeReport(draft: ReportDraft, now = Date.now()): { query?: DashboardQuery; errors: ReportErrors } {
  const errors: ReportErrors = {};
  if (draft.mode === "default") return { query: { bucket: draft.bucket }, errors };
  const validLocal = (value: string) => LOCAL_TIME.test(value) && !Number.isNaN(Date.parse(`${value}:00Z`)) && new Date(`${value}:00Z`).toISOString().slice(0, 16) === value;
  if (!validLocal(draft.from)) errors.from = "Enter a valid UTC date and time.";
  if (!validLocal(draft.to)) errors.to = "Enter a valid UTC date and time.";
  if (Object.keys(errors).length) return { errors };
  const from = `${draft.from}:00Z`;
  const to = `${draft.to}:00Z`;
  const span = Date.parse(to) - Date.parse(from);
  if (span <= 0) errors.range = "To must be later than From.";
  else if (Date.parse(to) > now + 60_000) errors.to = "To cannot be in the future.";
  else if (span > 366 * 86_400_000) errors.range = "Choose a range of 366 days or fewer.";
  const fromDate = new Date(from);
  const inclusiveTo = new Date(Date.parse(to) - 1);
  const dayFloor = (value: Date) => Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), value.getUTCDate());
  const weekFloor = (value: Date) => dayFloor(value) - ((value.getUTCDay() + 6) % 7) * 86_400_000;
  const bucketCount = draft.bucket === "day"
    ? Math.floor((dayFloor(inclusiveTo) - dayFloor(fromDate)) / 86_400_000) + 1
    : draft.bucket === "week"
      ? Math.floor((weekFloor(inclusiveTo) - weekFloor(fromDate)) / (7 * 86_400_000)) + 1
      : (inclusiveTo.getUTCFullYear() - fromDate.getUTCFullYear()) * 12 + inclusiveTo.getUTCMonth() - fromDate.getUTCMonth() + 1;
  if (!Object.keys(errors).length && bucketCount > 366) errors.range = "Choose a range that produces no more than 366 buckets.";
  return Object.keys(errors).length ? { errors } : { query: { from, to, bucket: draft.bucket }, errors };
}

export function dashboardUrl(query: DashboardQuery): string {
  const params = new URLSearchParams();
  if (query.from && query.to) { params.set("from", query.from); params.set("to", query.to); }
  if (query.bucket !== "day") params.set("bucket", query.bucket);
  const serialized = params.toString();
  return `/dashboard${serialized ? `?${serialized}` : ""}`;
}

export function dashboardApiPath(query: DashboardQuery): `/api/v1/${string}` {
  return dashboardUrl(query).replace("/dashboard", "/api/v1/analytics/dashboard") as `/api/v1/${string}`;
}

export function activityApiPath(query: DashboardQuery, page = 1, eventTypes: readonly ActivityEventType[] = [], snapshot?: string): `/api/v1/${string}` {
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  [...new Set(eventTypes)].forEach((eventType) => params.append("event_type", eventType));
  if (query.from && query.to) { params.set("from", query.from); params.set("to", query.to); }
  if (page > 1 && snapshot) params.set("snapshot_at", snapshot);
  return `/api/v1/activity-events?${params}`;
}

export async function readDashboard(query: DashboardQuery, signal?: AbortSignal): Promise<DashboardEnvelope> {
  return validateDashboardEnvelope(await apiEnvelopeRequest<unknown>(dashboardApiPath(query), { signal }));
}

export async function readActivity(query: DashboardQuery, role: DashboardRole, page = 1, eventTypes: readonly ActivityEventType[] = [], snapshot?: string, signal?: AbortSignal): Promise<ActivityEnvelope> {
  if (page > 1 && !snapshot) invalid();
  return validateActivityEnvelope(await apiEnvelopeRequest<unknown>(activityApiPath(query, page, eventTypes, snapshot), { signal }), role);
}

export type { DashboardActivityViewProps };
