import type {
  ChunkQuery,
  ChunkType,
  EvidenceQuery,
  RetrievalRole,
  ValidationState,
  WorkbenchMode,
  WorkbenchQuery,
} from "./types";

const ALL_KEYS = new Set([
  "mode", "page", "page_size", "chunk_type", "page_number", "retrieval_role",
  "section", "sort_by", "order", "field_path", "validation_state", "min_confidence",
]);
const CHUNK_TYPES = new Set<ChunkType>(["text", "table", "header", "list", "image", "unknown"]);
const RETRIEVAL_ROLES = new Set<RetrievalRole>(["parent", "child", "both"]);
const VALIDATION_STATES = new Set<ValidationState>(["valid", "invalid", "missing", "ambiguous", "unsupported"]);
const FIELD_PATH = /^[a-z][a-z0-9_]*(?:\.[A-Za-z0-9_-]+)+$/;
const CONFIDENCE = /^(?:0|[1-9]\d?|100)(?:\.\d{1,2})?$/;

export const DEFAULT_CHUNK_QUERY: ChunkQuery = { mode: "chunks", page: 1, pageSize: 50, order: "asc" };
export const DEFAULT_EVIDENCE_QUERY: EvidenceQuery = { mode: "evidence", page: 1, pageSize: 50 };

function one(params: URLSearchParams, key: string): string | undefined {
  const values = params.getAll(key);
  return values.length === 1 ? values[0] : undefined;
}

function positiveInteger(value: string | undefined): number | undefined {
  if (!value || !/^[1-9]\d*$/.test(value)) return undefined;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : undefined;
}

function pageSize(value: string | undefined): 20 | 50 | 100 | undefined {
  if (value === "20" || value === "50" || value === "100") return Number(value) as 20 | 50 | 100;
  return undefined;
}

export function serializeWorkbenchQuery(query: WorkbenchQuery): string {
  const params = new URLSearchParams();
  if (query.mode === "evidence") params.set("mode", "evidence");
  if (query.page !== 1) params.set("page", String(query.page));
  if (query.pageSize !== 50) params.set("page_size", String(query.pageSize));
  if (query.mode === "chunks") {
    if (query.chunkType) params.set("chunk_type", query.chunkType);
    if (query.pageNumber) params.set("page_number", String(query.pageNumber));
    if (query.retrievalRole) params.set("retrieval_role", query.retrievalRole);
    if (query.section) params.set("section", query.section);
    if (query.order !== "asc") params.set("order", query.order);
  } else {
    if (query.fieldPath) params.set("field_path", query.fieldPath);
    if (query.validationState) params.set("validation_state", query.validationState);
    if (query.minConfidence !== undefined) params.set("min_confidence", query.minConfidence);
  }
  return params.toString();
}

export function backendWorkbenchQuery(query: WorkbenchQuery): string {
  const params = new URLSearchParams(serializeWorkbenchQuery(query));
  params.delete("mode");
  params.set("page", String(query.page));
  params.set("page_size", String(query.pageSize));
  if (query.mode === "chunks") params.set("sort_by", "ordinal");
  return params.toString();
}

export function normalizeWorkbenchQuery(input: string | URLSearchParams) {
  const params = typeof input === "string" ? new URLSearchParams(input) : new URLSearchParams(input.toString());
  let reset = [...params.keys()].some((key) => !ALL_KEYS.has(key));
  reset ||= [...ALL_KEYS].some((key) => params.getAll(key).length > 1);

  const modeText = one(params, "mode");
  const mode: WorkbenchMode = modeText === "evidence" ? "evidence" : "chunks";
  if (modeText !== undefined && modeText !== "chunks" && modeText !== "evidence") reset = true;

  const pageText = one(params, "page");
  const sizeText = one(params, "page_size");
  const parsedPage = positiveInteger(pageText);
  const parsedSize = pageSize(sizeText);
  const page = parsedPage ?? 1;
  const selectedPageSize = parsedSize ?? 50;
  if (pageText !== undefined && parsedPage === undefined) reset = true;
  if (sizeText !== undefined && parsedSize === undefined) reset = true;

  let query: WorkbenchQuery;
  if (mode === "chunks") {
    const chunkTypeText = one(params, "chunk_type");
    const roleText = one(params, "retrieval_role");
    const pageNumberText = one(params, "page_number");
    const orderText = one(params, "order");
    const sortText = one(params, "sort_by");
    const rawSection = one(params, "section");
    const chunkType = chunkTypeText && CHUNK_TYPES.has(chunkTypeText as ChunkType) ? chunkTypeText as ChunkType : undefined;
    const retrievalRole = roleText && RETRIEVAL_ROLES.has(roleText as RetrievalRole) ? roleText as RetrievalRole : undefined;
    const pageNumber = positiveInteger(pageNumberText);
    const section = rawSection?.normalize("NFC").trim();
    const order = orderText === "desc" ? "desc" : "asc";
    if (chunkTypeText !== undefined && !chunkType) reset = true;
    if (roleText !== undefined && !retrievalRole) reset = true;
    if (pageNumberText !== undefined && pageNumber === undefined) reset = true;
    if (rawSection !== undefined && (!section || section.length > 255 || section !== rawSection)) reset = true;
    if (orderText !== undefined && orderText !== "asc" && orderText !== "desc") reset = true;
    if (sortText !== undefined && sortText !== "ordinal") reset = true;
    if (["field_path", "validation_state", "min_confidence"].some((key) => params.has(key))) reset = true;
    query = {
      mode: "chunks", page, pageSize: selectedPageSize, chunkType, pageNumber,
      retrievalRole, section: section && section.length <= 255 ? section : undefined, order,
    };
  } else {
    const fieldText = one(params, "field_path");
    const stateText = one(params, "validation_state");
    const confidenceText = one(params, "min_confidence");
    const fieldPath = fieldText && fieldText.length <= 255 && FIELD_PATH.test(fieldText) ? fieldText : undefined;
    const validationState = stateText && VALIDATION_STATES.has(stateText as ValidationState) ? stateText as ValidationState : undefined;
    const minConfidence = confidenceText && CONFIDENCE.test(confidenceText) && Number(confidenceText) <= 100 ? confidenceText : undefined;
    if (fieldText !== undefined && !fieldPath) reset = true;
    if (stateText !== undefined && !validationState) reset = true;
    if (confidenceText !== undefined && minConfidence === undefined) reset = true;
    if (["chunk_type", "page_number", "retrieval_role", "section", "sort_by", "order"].some((key) => params.has(key))) reset = true;
    query = { mode: "evidence", page, pageSize: selectedPageSize, fieldPath, validationState, minConfidence };
  }

  const canonical = serializeWorkbenchQuery(query);
  reset ||= canonical !== params.toString();
  return { query, canonical, reset };
}

export function queryForMode(mode: WorkbenchMode, pageSizeValue: 20 | 50 | 100): WorkbenchQuery {
  return mode === "chunks"
    ? { ...DEFAULT_CHUNK_QUERY, pageSize: pageSizeValue }
    : { ...DEFAULT_EVIDENCE_QUERY, pageSize: pageSizeValue };
}

export function queryWithPage(query: WorkbenchQuery, page: number): WorkbenchQuery {
  return { ...query, page: Math.max(1, Math.floor(page)) };
}

