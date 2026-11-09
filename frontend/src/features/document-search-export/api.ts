import { UUID_PATTERN } from "@/features/documents-list-upload-monitor/api";
import { apiEnvelopeRequest, apiResponseRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

import type {
  ExportFormat,
  ExportResource,
  FieldErrors,
  SearchDocumentStatus,
  SearchDraft,
  SearchEnvelope,
  SearchRequest,
  SearchResult,
} from "./types";

const STATUS = new Set(["pending_review", "approved", "rejected"]);
const TYPES = new Set(["commercial_invoice", "purchase_order", "packing_list"]);
const FORMATS = new Set(["csv", "xlsx", "json"]);
const EXPORT_STATUS = new Set(["queued", "processing", "completed", "failed", "expired"]);
const EXPORT_STAGES = new Set(["accepted", "generating", "packaging", "storing", "completed"]);
const MONEY = /^(0|[1-9]\d{0,11})(\.\d{1,2})?$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;

function invalid(): never {
  throw new ApiError("The service returned an unexpected response.", { code: "INVALID_API_RESPONSE" });
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid();
  return value as Record<string, unknown>;
}

function exact(value: Record<string, unknown>, keys: readonly string[]) {
  if (Object.keys(value).some((key) => !keys.includes(key))) invalid();
}

function integer(value: unknown, min: number, max = Number.MAX_SAFE_INTEGER): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= min && value <= max;
}

function utc(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value)) && /(?:Z|[+-]\d{2}:\d{2})$/.test(value);
}

function nullable(value: unknown, predicate: (entry: unknown) => boolean): boolean {
  return value === null || predicate(value);
}

function safeDate(value: unknown): value is string {
  if (typeof value !== "string" || !DATE.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function compareMoney(left: string, right: string): number {
  const scale = (value: string) => {
    const [whole, fraction = ""] = value.split(".");
    return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  };
  const a = scale(left);
  const b = scale(right);
  return a < b ? -1 : a > b ? 1 : 0;
}

function validLocalDateTime(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value) && !Number.isNaN(Date.parse(`${value}:00Z`));
}

export function serializeSearch(draft: SearchDraft): { request?: SearchRequest; errors: FieldErrors } {
  const errors: FieldErrors = {};
  const query = draft.query.trim();
  const supplier = draft.supplier.trim();
  const currency = draft.currency.trim().toUpperCase();
  if (query && (Array.from(query).length < 3 || Array.from(query).length > 500)) errors.query = "Use 3 to 500 characters.";
  if (supplier.length > 255) errors.supplier = "Use 255 characters or fewer.";
  if (currency && !/^[A-Z]{3}$/.test(currency)) errors.currency = "Use a three-letter currency code.";
  for (const key of ["invoice_date_from", "invoice_date_to"] as const) {
    if (draft[key] && !safeDate(draft[key])) errors[key] = "Enter a real date.";
  }
  for (const key of ["uploaded_from", "uploaded_to"] as const) {
    if (draft[key] && !validLocalDateTime(draft[key])) errors[key] = "Enter a valid UTC date and time.";
  }
  for (const key of ["min_total", "max_total"] as const) {
    if (draft[key] && !MONEY.test(draft[key])) errors[key] = "Use a non-negative amount with at most two decimals.";
  }
  if (draft.invoice_date_from && draft.invoice_date_to && draft.invoice_date_from > draft.invoice_date_to) errors.invoice_date_to = "End date must not be before start date.";
  if (draft.uploaded_from && draft.uploaded_to && draft.uploaded_from > draft.uploaded_to) errors.uploaded_to = "End time must not be before start time.";
  if (MONEY.test(draft.min_total) && MONEY.test(draft.max_total) && compareMoney(draft.min_total, draft.max_total) > 0) errors.max_total = "Maximum must not be below minimum.";
  const hasCriteria = Boolean(query || draft.document_statuses.length || draft.document_type || supplier || currency || draft.invoice_date_from || draft.invoice_date_to || draft.uploaded_from || draft.uploaded_to || draft.min_total || draft.max_total);
  if (!hasCriteria) errors.criteria = "Enter search text or at least one filter.";
  if (draft.sort_by === "relevance" && !query) errors.sort_by = "Relevance sorting requires search text.";
  if (Object.keys(errors).length) return { errors };
  return {
    errors,
    request: {
      ...(query ? { query } : {}),
      ...(draft.document_statuses.length ? { document_statuses: [...new Set(draft.document_statuses)] } : {}),
      ...(draft.document_type ? { document_type: draft.document_type } : {}),
      ...(supplier ? { supplier } : {}),
      ...(currency ? { currency } : {}),
      ...(draft.invoice_date_from ? { invoice_date_from: draft.invoice_date_from } : {}),
      ...(draft.invoice_date_to ? { invoice_date_to: draft.invoice_date_to } : {}),
      ...(draft.uploaded_from ? { uploaded_from: `${draft.uploaded_from}:00Z` } : {}),
      ...(draft.uploaded_to ? { uploaded_to: `${draft.uploaded_to}:00Z` } : {}),
      ...(draft.min_total ? { min_total: draft.min_total } : {}),
      ...(draft.max_total ? { max_total: draft.max_total } : {}),
      sort_by: draft.sort_by,
      order: draft.order,
      page: draft.page,
      page_size: draft.page_size,
    },
  };
}

function meta(value: unknown) {
  const item = record(value);
  exact(item, ["timestamp", "request_id"]);
  if (!utc(item.timestamp) || typeof item.request_id !== "string" || !item.request_id || item.request_id.length > 128) invalid();
  return item as unknown as SearchEnvelope["meta"];
}

function route(value: unknown, documentId: string, review = false): value is string {
  return typeof value === "string" && value === `/documents/${documentId}${review ? "/review" : ""}`;
}

function searchResult(value: unknown, semantic: boolean): SearchResult {
  const item = record(value);
  const keys = ["document_id", "file_name", "document_type", "status", "created_at", "invoice_id", "invoice_number", "supplier_name", "date_issued", "currency", "grand_total", "is_math_valid", "review_revision", "relevance_score", "matching_excerpt", "matching_chunk_id", "matching_page_start", "matching_page_end", "export_eligible", "document_url", "review_url"] as const;
  exact(item, keys);
  const textOrNull = (entry: unknown, max: number) => nullable(entry, (candidate) => typeof candidate === "string" && candidate.length <= max);
  const pageOrNull = (entry: unknown) => nullable(entry, (candidate) => integer(candidate, 1));
  if (typeof item.document_id !== "string" || !UUID_PATTERN.test(item.document_id) || typeof item.file_name !== "string" || !item.file_name || item.file_name.length > 255
    || !TYPES.has(item.document_type as string) || !STATUS.has(item.status as string) || !utc(item.created_at)
    || typeof item.invoice_id !== "string" || !UUID_PATTERN.test(item.invoice_id) || !textOrNull(item.invoice_number, 100) || !textOrNull(item.supplier_name, 255)
    || !nullable(item.date_issued, safeDate) || !nullable(item.currency, (entry) => typeof entry === "string" && /^[A-Z]{3}$/.test(entry))
    || !nullable(item.grand_total, (entry) => typeof entry === "string" && /^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/.test(entry))
    || typeof item.is_math_valid !== "boolean" || !integer(item.review_revision, 0)
    || !nullable(item.relevance_score, (entry) => typeof entry === "number" && Number.isFinite(entry) && entry >= -1 && entry <= 1)
    || !textOrNull(item.matching_excerpt, 500) || !nullable(item.matching_chunk_id, (entry) => typeof entry === "string" && UUID_PATTERN.test(entry))
    || !pageOrNull(item.matching_page_start) || !pageOrNull(item.matching_page_end) || typeof item.export_eligible !== "boolean"
    || !route(item.document_url, item.document_id) || !(item.review_url === null || route(item.review_url, item.document_id, true))) invalid();
  if (!semantic && [item.relevance_score, item.matching_excerpt, item.matching_chunk_id, item.matching_page_start, item.matching_page_end].some((entry) => entry !== null)) invalid();
  if (item.matching_page_start !== null && item.matching_page_end !== null && (item.matching_page_start as number) > (item.matching_page_end as number)) invalid();
  return item as unknown as SearchResult;
}

export function validateSearchEnvelope(value: unknown, semantic: boolean): SearchEnvelope {
  const item = record(value);
  exact(item, ["success", "data", "message", "meta", "pagination"]);
  const pagination = record(item.pagination);
  exact(pagination, ["page", "page_size", "total_records", "total_pages", "has_next", "has_prev"]);
  if (item.success !== true || !Array.isArray(item.data) || typeof item.message !== "string" || !integer(pagination.page, 1)
    || !integer(pagination.page_size, 1, 100) || !integer(pagination.total_records, 0) || !integer(pagination.total_pages, 0)
    || typeof pagination.has_next !== "boolean" || typeof pagination.has_prev !== "boolean") invalid();
  const data = item.data.map((entry) => searchResult(entry, semantic));
  if (pagination.total_pages === 0 ? pagination.page !== 1 || data.length !== 0 : pagination.page > (pagination.total_pages as number)) invalid();
  return { success: true, data, message: item.message, meta: meta(item.meta), pagination: pagination as unknown as SearchEnvelope["pagination"] };
}

const RESOURCE_KEYS = ["export_id", "format", "mode", "status", "progress_percentage", "current_stage", "selected_document_count", "exported_document_count", "row_count", "created_at", "started_at", "completed_at", "artifact_expires_at", "status_url", "download_url"] as const;

function exportResource(value: unknown, allowErrors: boolean): ExportResource {
  const item = record(value);
  exact(item, allowErrors ? [...RESOURCE_KEYS, "error_code", "error_message"] : RESOURCE_KEYS);
  if (typeof item.export_id !== "string" || !UUID_PATTERN.test(item.export_id) || !FORMATS.has(item.format as string)
    || (item.mode !== "synchronous" && item.mode !== "asynchronous") || !EXPORT_STATUS.has(item.status as string) || !integer(item.progress_percentage, 0, 100)
    || !EXPORT_STAGES.has(item.current_stage as string) || !integer(item.selected_document_count, 1, 50000) || !integer(item.exported_document_count, 0, 50000)
    || !integer(item.row_count, 0, 1000000) || !utc(item.created_at) || !nullable(item.started_at, utc) || !nullable(item.completed_at, utc)
    || !nullable(item.artifact_expires_at, utc) || item.status_url !== `/api/v1/exports/${item.export_id}`
    || !(item.download_url === null || item.download_url === `/api/v1/exports/${item.export_id}/download`)
    || (allowErrors && !(item.error_code === undefined || item.error_code === null || typeof item.error_code === "string" && item.error_code.length <= 100))
    || (allowErrors && !(item.error_message === undefined || item.error_message === null || typeof item.error_message === "string" && item.error_message.length <= 1000))) invalid();
  if (item.status === "completed" && (item.progress_percentage !== 100 || item.current_stage !== "completed" || item.completed_at === null || item.artifact_expires_at === null || item.download_url === null)) invalid();
  if (item.status !== "completed" && item.download_url !== null) invalid();
  return item as unknown as ExportResource;
}

function validateResourceEnvelope(value: unknown, allowErrors: boolean): ExportResource {
  const envelope = record(value);
  exact(envelope, ["success", "data", "message", "meta"]);
  if (envelope.success !== true || typeof envelope.message !== "string") invalid();
  meta(envelope.meta);
  return exportResource(envelope.data, allowErrors);
}

export function validateExportEnvelope(value: unknown, statusResponse = false): ExportResource {
  return validateResourceEnvelope(value, statusResponse);
}

export async function searchDocuments(request: SearchRequest, signal?: AbortSignal): Promise<SearchEnvelope> {
  const raw = await apiEnvelopeRequest<unknown>("/api/v1/documents/search", { method: "POST", body: request as unknown as Record<string, unknown>, signal });
  return validateSearchEnvelope(raw, Boolean(request.query));
}

export async function createExport(documentIds: string[], format: ExportFormat, idempotencyKey: string, signal?: AbortSignal): Promise<{ status: number; resource: ExportResource }> {
  if (!documentIds.length || documentIds.some((id) => !UUID_PATTERN.test(id)) || !FORMATS.has(format)) invalid();
  const response = await apiResponseRequest<unknown>("/api/v1/exports", {
    method: "POST",
    body: { format, document_ids: documentIds },
    headers: { "Idempotency-Key": idempotencyKey },
    signal,
  });
  const resource = validateResourceEnvelope(response.data, false);
  if (!((response.status === 201 && resource.mode === "synchronous" && resource.status === "completed")
    || (response.status === 202 && resource.mode === "asynchronous" && (resource.status === "queued" || resource.status === "processing")))) invalid();
  return { status: response.status, resource };
}

export async function readExport(exportId: string, signal?: AbortSignal): Promise<ExportResource> {
  if (!UUID_PATTERN.test(exportId)) invalid();
  const raw = await apiEnvelopeRequest<unknown>(`/api/v1/exports/${exportId}`, { signal });
  return validateResourceEnvelope(raw, true);
}

export function statusTone(status: ExportResource["status"]): "technical" | "success" | "warning" | "danger" {
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "expired") return "warning";
  return "technical";
}

export function publicExportError(code: string | null | undefined): string {
  const messages: Record<string, string> = {
    EXPORT_SOURCE_CHANGED: "The approved records changed. Create a new export from current results.",
    EXPORT_NOT_READY: "The artifact is not ready yet. Refresh its status.",
    EXPORT_EXPIRED: "This artifact has expired. Create a new export.",
    EXPORT_LIMIT_EXCEEDED: "This export exceeds a supported limit. Reduce the selection.",
    EXPORT_SELECTION_NOT_ELIGIBLE: "One or more selected records are no longer exportable. Search again.",
    EXPORT_SELECTION_NOT_FOUND: "One or more selected records are unavailable. Search again.",
  };
  return code && messages[code] ? messages[code] : "The export could not be completed safely.";
}

export const SEARCH_STATUSES = [...STATUS] as SearchDocumentStatus[];
