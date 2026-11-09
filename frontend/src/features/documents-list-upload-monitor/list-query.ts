import type { DocumentListQuery, DocumentStatus, DocumentType } from "./types";

export const DEFAULT_DOCUMENT_QUERY: DocumentListQuery = {
  page: 1,
  pageSize: 20,
  sortBy: "created_at",
  order: "desc",
};

const KEYS = ["page", "page_size", "status", "doc_type", "from_date", "to_date", "sort_by", "order"] as const;
const STATUS = new Set<DocumentStatus>(["queued", "partitioning", "chunking", "vectorizing", "extracting", "pending_review", "approved", "rejected", "failed"]);
const TYPES = new Set<DocumentType>(["commercial_invoice", "purchase_order", "packing_list"]);
const SORT = new Set<DocumentListQuery["sortBy"]>(["created_at", "updated_at", "file_name"]);

function one(params: URLSearchParams, key: string): string | undefined {
  const values = params.getAll(key);
  return values.length === 1 ? values[0] : undefined;
}

function validDate(value: string | undefined): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

export function serializeDocumentQuery(query: DocumentListQuery): string {
  const params = new URLSearchParams();
  if (query.page !== 1) params.set("page", String(query.page));
  if (query.pageSize !== 20) params.set("page_size", String(query.pageSize));
  if (query.status) params.set("status", query.status);
  if (query.documentType) params.set("doc_type", query.documentType);
  if (query.fromDate) params.set("from_date", query.fromDate);
  if (query.toDate) params.set("to_date", query.toDate);
  if (query.sortBy !== "created_at") params.set("sort_by", query.sortBy);
  if (query.order !== "desc") params.set("order", query.order);
  return params.toString();
}

export function backendDocumentQuery(query: DocumentListQuery): string {
  const params = new URLSearchParams(serializeDocumentQuery(query));
  params.set("page", String(query.page));
  params.set("page_size", String(query.pageSize));
  params.set("sort_by", query.sortBy);
  params.set("order", query.order);
  return params.toString();
}

export function normalizeDocumentQuery(input: string | URLSearchParams, viewer = false) {
  const params = typeof input === "string" ? new URLSearchParams(input) : new URLSearchParams(input.toString());
  let reset = [...params.keys()].some((key) => !KEYS.includes(key as typeof KEYS[number]));
  reset ||= KEYS.some((key) => params.getAll(key).length > 1);

  const pageText = one(params, "page");
  const sizeText = one(params, "page_size");
  const statusText = one(params, "status");
  const typeText = one(params, "doc_type");
  const sortText = one(params, "sort_by");
  const orderText = one(params, "order");
  let fromDate = one(params, "from_date");
  let toDate = one(params, "to_date");

  const page = pageText && /^[1-9]\d*$/.test(pageText) ? Number(pageText) : 1;
  if (pageText !== undefined && (!Number.isSafeInteger(page) || page < 1)) reset = true;
  const pageSize = sizeText && ["20", "50", "100"].includes(sizeText) ? Number(sizeText) as 20 | 50 | 100 : 20;
  if (sizeText !== undefined && !["20", "50", "100"].includes(sizeText)) reset = true;

  const status = !viewer && statusText && STATUS.has(statusText as DocumentStatus) ? statusText as DocumentStatus : undefined;
  if (statusText !== undefined && (viewer || !status)) reset = true;
  const documentType = typeText && TYPES.has(typeText as DocumentType) ? typeText as DocumentType : undefined;
  if (typeText !== undefined && !documentType) reset = true;
  const sortBy = sortText && SORT.has(sortText as DocumentListQuery["sortBy"])
    ? sortText as DocumentListQuery["sortBy"] : "created_at";
  if (sortText !== undefined && !SORT.has(sortText as DocumentListQuery["sortBy"])) reset = true;
  const order = orderText === "asc" || orderText === "desc" ? orderText : "desc";
  if (orderText !== undefined && orderText !== "asc" && orderText !== "desc") reset = true;

  if (fromDate !== undefined && !validDate(fromDate)) { fromDate = undefined; reset = true; }
  if (toDate !== undefined && !validDate(toDate)) { toDate = undefined; reset = true; }
  if (fromDate && toDate && fromDate > toDate) { fromDate = undefined; toDate = undefined; reset = true; }

  const query: DocumentListQuery = { page, pageSize, status, documentType, fromDate, toDate, sortBy, order };
  const canonical = serializeDocumentQuery(query);
  reset ||= canonical !== params.toString();
  return { query, canonical, reset };
}

export function documentQueryWithPage(query: DocumentListQuery, page: number): string {
  return serializeDocumentQuery({ ...query, page: Math.max(1, Math.floor(page)) });
}
