import { UUID_PATTERN } from "@/features/documents-list-upload-monitor/api";

import {
  EMPTY_SEARCH_DRAFT,
  type SearchDocumentStatus,
  type SearchDraft,
  type SearchUrlState,
} from "./types";

const STATUSES: SearchDocumentStatus[] = ["pending_review", "approved", "rejected"];
const TYPES = new Set(["commercial_invoice", "purchase_order", "packing_list"]);
const SORTS = new Set(["relevance", "date_issued", "grand_total", "created_at"]);
const ORDERS = new Set(["asc", "desc"]);
const PAGE_SIZES = new Set([20, 50, 100]);
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const UTC_MINUTE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;
const MONEY = /^(0|[1-9]\d{0,11})(\.\d{1,2})?$/;
const CURRENCY = /^[A-Z]{3}$/;

function one(params: URLSearchParams, key: string): string | null {
  const values = params.getAll(key);
  return values.length === 1 ? values[0] : null;
}

function validDate(value: string | null): value is string {
  if (!value || !DATE.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

export function parseSearchUrl(params: URLSearchParams): SearchUrlState {
  const draft: SearchDraft = { ...EMPTY_SEARCH_DRAFT, document_statuses: [] };
  const rawStatuses = params.getAll("status");
  if (rawStatuses.every((value) => STATUSES.includes(value as SearchDocumentStatus))) {
    draft.document_statuses = STATUSES.filter((status) => rawStatuses.includes(status));
  }
  const documentType = one(params, "document_type");
  if (documentType && TYPES.has(documentType)) draft.document_type = documentType as SearchDraft["document_type"];
  const supplier = one(params, "supplier");
  if (supplier && supplier.length <= 255) draft.supplier = supplier;
  const currency = one(params, "currency")?.toUpperCase() ?? null;
  if (currency && CURRENCY.test(currency)) draft.currency = currency;
  for (const key of ["invoice_date_from", "invoice_date_to"] as const) {
    const value = one(params, key);
    if (validDate(value)) draft[key] = value;
  }
  for (const key of ["uploaded_from", "uploaded_to"] as const) {
    const value = one(params, key);
    if (value && UTC_MINUTE.test(value) && !Number.isNaN(Date.parse(`${value}:00Z`))) draft[key] = value;
  }
  for (const key of ["min_total", "max_total"] as const) {
    const value = one(params, key);
    if (value && MONEY.test(value)) draft[key] = value;
  }
  const sort = one(params, "sort_by");
  if (sort && SORTS.has(sort)) draft.sort_by = sort as SearchDraft["sort_by"];
  const order = one(params, "order");
  if (order && ORDERS.has(order)) draft.order = order as SearchDraft["order"];
  const page = Number(one(params, "page"));
  if (Number.isSafeInteger(page) && page >= 1) draft.page = page;
  const pageSize = Number(one(params, "page_size"));
  if (PAGE_SIZES.has(pageSize)) draft.page_size = pageSize as SearchDraft["page_size"];
  const exportId = one(params, "export_id");
  return {
    draft,
    exportId: exportId && UUID_PATTERN.test(exportId) ? exportId : null,
    hasStructuredCriteria: hasStructuredCriteria(draft),
  };
}

export function hasStructuredCriteria(draft: SearchDraft): boolean {
  return Boolean(
    draft.document_statuses.length || draft.document_type || draft.supplier.trim() || draft.currency.trim()
    || draft.invoice_date_from || draft.invoice_date_to || draft.uploaded_from || draft.uploaded_to
    || draft.min_total || draft.max_total,
  );
}

export function canonicalSearchParams(draft: SearchDraft, exportId?: string | null): string {
  const params = new URLSearchParams();
  for (const status of STATUSES) if (draft.document_statuses.includes(status)) params.append("status", status);
  if (draft.document_type) params.set("document_type", draft.document_type);
  if (draft.supplier.trim()) params.set("supplier", draft.supplier.trim());
  if (draft.currency.trim()) params.set("currency", draft.currency.trim().toUpperCase());
  for (const key of ["invoice_date_from", "invoice_date_to", "uploaded_from", "uploaded_to", "min_total", "max_total"] as const) {
    if (draft[key]) params.set(key, draft[key]);
  }
  if (draft.sort_by !== "created_at") params.set("sort_by", draft.sort_by);
  if (draft.order !== "desc") params.set("order", draft.order);
  if (draft.page !== 1) params.set("page", String(draft.page));
  if (draft.page_size !== 20) params.set("page_size", String(draft.page_size));
  if (exportId && UUID_PATTERN.test(exportId)) params.set("export_id", exportId);
  return params.toString();
}

export function normalizeSearchUrl(params: URLSearchParams): string {
  const state = parseSearchUrl(params);
  return canonicalSearchParams(state.draft, state.exportId);
}
