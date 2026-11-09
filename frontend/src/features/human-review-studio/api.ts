import { apiEnvelopeRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { UUID_PATTERN } from "@/features/documents-list-upload-monitor/api";
import type { PaginationData } from "@/features/documents-list-upload-monitor/types";
import type { ReviewInvoice, RuleResult, ValidationReport } from "@/features/document-detail-chunk-inspector/types";

import type {
  AuditAction,
  AuditChange,
  AuditChangeValue,
  AuditEnvelope,
  AuditEvent,
  InvoiceCandidate,
  MutationBody,
  MutationData,
  PreviewData,
  PreviewLineItem,
  ReviewCandidate,
  ReviewEnvelope,
} from "./types";

const AUDIT_ACTIONS = new Set<AuditAction>(["field_edited", "approved", "rejected", "reopened"]);
const REVIEW_STATUSES = new Set(["pending_review", "approved", "rejected"]);
const USER_ACTIONS = new Set(["save", "approve", "reject", "reopen"]);
const RULE_STATUSES = new Set(["passed", "failed", "missing", "not_applicable"]);
const CHANGE_KINDS = new Set(["set", "add", "remove", "reorder"]);
const DECIMAL = /^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/;

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

function text(value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): value is string {
  return typeof value === "string" && value.length >= min && value.length <= max;
}

function integer(value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= min && value <= max;
}

function nullableText(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function decimal(value: unknown): value is string | null {
  return value === null || typeof value === "string" && DECIMAL.test(value);
}

function dateTime(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value)) && /(?:Z|[+-]\d{2}:\d{2})$/.test(value);
}

function meta(value: unknown) {
  const item = record(value);
  exact(item, ["timestamp", "request_id"]);
  if (!dateTime(item.timestamp) || !text(item.request_id, 1, 128)) invalid();
  return item as { timestamp: string; request_id: string };
}

function envelope(value: unknown) {
  const item = record(value);
  exact(item, ["success", "data", "message", "meta", "pagination"]);
  if (item.success !== true || !text(item.message)) invalid();
  return item;
}

function invoiceCandidate(value: unknown): InvoiceCandidate {
  const item = record(value);
  const keys = ["invoice_number", "supplier_name", "supplier_tax_id", "buyer_name", "date_issued", "due_date", "currency", "subtotal", "tax_amount", "discount_amount", "grand_total"] as const;
  exact(item, keys);
  if (keys.slice(0, 7).some((key) => !nullableText(item[key])) || keys.slice(7).some((key) => !decimal(item[key]))) invalid();
  return item as unknown as InvoiceCandidate;
}

function ruleResult(value: unknown): RuleResult {
  const item = record(value);
  exact(item, ["rule_id", "scope_key", "status", "observed_value", "expected_value", "difference", "epsilon", "message_code", "blocks_approval"]);
  const scalar = (entry: unknown) => entry === undefined || entry === null || typeof entry === "string" || typeof entry === "boolean" || integer(entry, Number.MIN_SAFE_INTEGER);
  if (!text(item.rule_id, 1, 64) || !text(item.scope_key, 1, 255) || !RULE_STATUSES.has(item.status as string)
    || !scalar(item.observed_value) || !scalar(item.expected_value) || (item.difference !== undefined && !decimal(item.difference))
    || (item.epsilon !== undefined && !decimal(item.epsilon)) || !text(item.message_code, 1, 100) || typeof item.blocks_approval !== "boolean") invalid();
  return item as unknown as RuleResult;
}

function validation(value: unknown): ValidationReport {
  const item = record(value);
  exact(item, ["validation_version", "is_math_valid", "approval_eligible", "summary", "results", "warnings", "blocking_reasons"]);
  const summary = record(item.summary);
  exact(summary, ["passed", "failed", "missing", "not_applicable"]);
  if ((item.validation_version !== undefined && item.validation_version !== "human-review-v1") || typeof item.is_math_valid !== "boolean"
    || typeof item.approval_eligible !== "boolean" || Object.values(summary).some((entry) => !integer(entry)) || !Array.isArray(item.results)
    || (item.warnings !== undefined && (!Array.isArray(item.warnings) || item.warnings.some((entry) => !text(entry))))
    || (item.blocking_reasons !== undefined && (!Array.isArray(item.blocking_reasons) || item.blocking_reasons.some((entry) => !text(entry))))) invalid();
  return { ...(item as unknown as ValidationReport), summary: summary as unknown as ValidationReport["summary"], results: item.results.map(ruleResult) };
}

function previewLine(value: unknown): PreviewLineItem {
  const item = record(value);
  exact(item, ["line_item_id", "client_correlation_key", "origin", "line_order", "description", "hs_code", "quantity", "unit_price", "tax_amount", "total_price", "calculated_total_price"]);
  if (!(item.line_item_id === null || text(item.line_item_id) && UUID_PATTERN.test(item.line_item_id)) || !nullableText(item.client_correlation_key)
    || (item.origin !== "extracted" && item.origin !== "reviewer_added") || !integer(item.line_order, 1, 500)
    || !nullableText(item.description) || !nullableText(item.hs_code)
    || ["quantity", "unit_price", "tax_amount", "total_price", "calculated_total_price"].some((key) => !decimal(item[key]))) invalid();
  return item as unknown as PreviewLineItem;
}

export function validatePreviewEnvelope(value: unknown): ReviewEnvelope<PreviewData> {
  const item = envelope(value);
  if ("pagination" in item) invalid();
  const data = record(item.data);
  exact(data, ["review_revision", "invoice", "line_items", "calculated_subtotal", "calculated_grand_total", "validation"]);
  if (!integer(data.review_revision) || !Array.isArray(data.line_items) || !decimal(data.calculated_subtotal) || !decimal(data.calculated_grand_total)) invalid();
  return {
    success: true,
    data: {
      review_revision: data.review_revision,
      invoice: invoiceCandidate(data.invoice),
      line_items: data.line_items.map(previewLine),
      calculated_subtotal: data.calculated_subtotal,
      calculated_grand_total: data.calculated_grand_total,
      validation: validation(data.validation),
    },
    message: item.message as string,
    meta: meta(item.meta),
  };
}

function reviewInvoice(value: unknown): ReviewInvoice {
  const item = record(value);
  exact(item, ["invoice_id", "invoice_number", "supplier_name", "supplier_tax_id", "buyer_name", "date_issued", "due_date", "currency", "subtotal", "tax_amount", "discount_amount", "grand_total", "is_math_valid", "line_items"]);
  if (!text(item.invoice_id) || !UUID_PATTERN.test(item.invoice_id) || typeof item.is_math_valid !== "boolean" || !Array.isArray(item.line_items)) invalid();
  invoiceCandidate({
    invoice_number: item.invoice_number,
    supplier_name: item.supplier_name,
    supplier_tax_id: item.supplier_tax_id,
    buyer_name: item.buyer_name,
    date_issued: item.date_issued,
    due_date: item.due_date,
    currency: item.currency,
    subtotal: item.subtotal,
    tax_amount: item.tax_amount,
    discount_amount: item.discount_amount,
    grand_total: item.grand_total,
  });
  const lines = item.line_items.map((entry) => {
    const line = record(entry);
    exact(line, ["line_item_id", "origin", "line_order", "description", "hs_code", "quantity", "unit_price", "tax_amount", "total_price"]);
    if (!text(line.line_item_id) || !UUID_PATTERN.test(line.line_item_id) || (line.origin !== "extracted" && line.origin !== "reviewer_added")
      || !integer(line.line_order, 1, 500) || !nullableText(line.description) || !nullableText(line.hs_code)
      || ["quantity", "unit_price", "tax_amount", "total_price"].some((key) => !decimal(line[key]))) invalid();
    return line;
  });
  return { ...(item as unknown as ReviewInvoice), line_items: lines as unknown as ReviewInvoice["line_items"] };
}

export function validateMutationEnvelope(value: unknown): ReviewEnvelope<MutationData> {
  const item = envelope(value);
  if ("pagination" in item) invalid();
  const data = record(item.data);
  exact(data, ["document_id", "status", "review_revision", "invoice", "latest_review_validation", "audit_event_id", "permitted_actions"]);
  if (!text(data.document_id) || !UUID_PATTERN.test(data.document_id) || !REVIEW_STATUSES.has(data.status as string) || !integer(data.review_revision, 1)
    || !text(data.audit_event_id) || !UUID_PATTERN.test(data.audit_event_id) || !Array.isArray(data.permitted_actions)
    || data.permitted_actions.some((action) => !USER_ACTIONS.has(action as string))) invalid();
  return {
    success: true,
    data: {
      ...(data as unknown as MutationData),
      invoice: reviewInvoice(data.invoice),
      latest_review_validation: data.latest_review_validation === null ? null : validation(data.latest_review_validation),
    },
    message: item.message as string,
    meta: meta(item.meta),
  };
}

function changeValue(value: unknown): value is AuditChangeValue {
  if (value === null || typeof value === "string" || typeof value === "boolean" || integer(value, Number.MIN_SAFE_INTEGER)) return true;
  if (Array.isArray(value)) return value.length <= 100 && value.every((entry) => entry === null || typeof entry === "string" || typeof entry === "boolean" || integer(entry, Number.MIN_SAFE_INTEGER));
  if (value && typeof value === "object") return Object.keys(value).length <= 100 && Object.values(value).every((entry) => entry === null || typeof entry === "string" || typeof entry === "boolean" || integer(entry, Number.MIN_SAFE_INTEGER));
  return false;
}

function auditChange(value: unknown): AuditChange {
  const item = record(value);
  exact(item, ["field_path", "change_kind", "old_value", "new_value"]);
  if (!text(item.field_path, 1, 255) || !CHANGE_KINDS.has(item.change_kind as string)
    || (item.old_value !== undefined && !changeValue(item.old_value)) || (item.new_value !== undefined && !changeValue(item.new_value))) invalid();
  return item as unknown as AuditChange;
}

function auditEvent(value: unknown): AuditEvent {
  const item = record(value);
  exact(item, ["audit_event_id", "actor_user_id", "actor_display_name", "action", "from_status", "to_status", "review_revision", "reason", "note", "request_id", "created_at", "changes"]);
  if (!text(item.audit_event_id) || !UUID_PATTERN.test(item.audit_event_id) || !text(item.actor_user_id) || !UUID_PATTERN.test(item.actor_user_id)
    || !nullableText(item.actor_display_name) || !AUDIT_ACTIONS.has(item.action as AuditAction) || !REVIEW_STATUSES.has(item.from_status as string)
    || !REVIEW_STATUSES.has(item.to_status as string) || !integer(item.review_revision, 1) || !nullableText(item.reason) || !nullableText(item.note)
    || !text(item.request_id, 1, 128) || !dateTime(item.created_at) || !Array.isArray(item.changes)) invalid();
  return { ...(item as unknown as AuditEvent), changes: item.changes.map(auditChange) };
}

function pagination(value: unknown): PaginationData {
  const item = record(value);
  exact(item, ["page", "page_size", "total_records", "total_pages", "has_next", "has_prev"]);
  if (!integer(item.page, 1) || !integer(item.page_size, 1, 100) || !integer(item.total_records) || !integer(item.total_pages)
    || typeof item.has_next !== "boolean" || typeof item.has_prev !== "boolean") invalid();
  return item as unknown as PaginationData;
}

export function validateAuditEnvelope(value: unknown): AuditEnvelope {
  const item = envelope(value);
  if (!Array.isArray(item.data) || !("pagination" in item)) invalid();
  return { success: true, data: item.data.map(auditEvent), message: item.message as string, meta: meta(item.meta), pagination: pagination(item.pagination) };
}

export async function previewReview(documentId: string, candidate: ReviewCandidate, signal?: AbortSignal) {
  const raw = await apiEnvelopeRequest<unknown>(`/api/v1/documents/${documentId}/review-validations`, { method: "POST", body: candidate as unknown as Record<string, unknown>, signal });
  return validatePreviewEnvelope(raw);
}

export async function mutateReview(documentId: string, body: MutationBody, idempotencyKey: string, signal?: AbortSignal) {
  const raw = await apiEnvelopeRequest<unknown>(`/api/v1/documents/${documentId}/review`, {
    method: "PUT",
    body: body as unknown as Record<string, unknown>,
    headers: { "idempotency-key": idempotencyKey },
    signal,
  });
  return validateMutationEnvelope(raw);
}

export async function readAudit(documentId: string, page: number, action?: AuditAction, signal?: AbortSignal) {
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (action) params.set("action", action);
  const raw = await apiEnvelopeRequest<unknown>(`/api/v1/documents/${documentId}/audit-logs?${params}`, { signal });
  return validateAuditEnvelope(raw);
}
