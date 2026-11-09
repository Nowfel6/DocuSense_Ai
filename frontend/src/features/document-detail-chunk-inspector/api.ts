import { apiEnvelopeRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { MAX_DOCUMENT_BYTES } from "@/features/documents-list-upload-monitor/capabilities";
import { UUID_PATTERN } from "@/features/documents-list-upload-monitor/api";
import type {
  DocumentStatus,
  DocumentType,
  PaginationData,
} from "@/features/documents-list-upload-monitor/types";

import { isSafeSourceUrl } from "./source-view";
import type {
  BoundingBox,
  ChunkItem,
  ChunkListEnvelope,
  DocumentDetail,
  DocumentDetailEnvelope,
  EmbeddingStatus,
  EvidenceItem,
  EvidenceResponse,
  EvidenceSummary,
  ExtractionEvidenceData,
  ExtractionRunInfo,
  ReviewInvoice,
  ReviewLineItem,
  RuleResult,
  RuleStatus,
  SourceView,
  StructuredTable,
  TableCell,
  TableRow,
  UserAction,
  ValidationReport,
  ValidationRuleSummary,
  ValidationState,
  ValidationSummary,
  WorkbenchQuery,
} from "./types";
import { backendWorkbenchQuery } from "./workbench-query";

const DOCUMENT_STATUSES = new Set<DocumentStatus>(["queued", "partitioning", "chunking", "vectorizing", "extracting", "pending_review", "approved", "rejected", "failed"]);
const DOCUMENT_TYPES = new Set<DocumentType>(["commercial_invoice", "purchase_order", "packing_list"]);
const MIME_TYPES = new Set(["application/pdf", "image/png", "image/jpeg"]);
const ACTIONS = new Set<UserAction>(["save", "approve", "reject", "reopen"]);
const VALIDATION_STATES = new Set<ValidationState>(["valid", "invalid", "missing", "ambiguous", "unsupported"]);
const RULE_STATUSES = new Set<RuleStatus>(["passed", "failed", "missing", "not_applicable"]);
const CHUNK_TYPES = new Set(["text", "table", "header", "list", "image", "unknown"]);
const RETRIEVAL_ROLES = new Set(["parent", "child", "both"]);
const EMBEDDING_STATUSES = new Set<EmbeddingStatus>(["pending", "completed", "failed", "not_required"]);
const ROTATIONS = new Set([0, 90, 180, 270]);
const DECIMAL = /^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/;
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const UNSAFE_FILENAME = /[\\/\u0000-\u001f\u007f]/;

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function invalidResponse(): never {
  throw new ApiError("The service returned an unexpected response.", { code: "INVALID_API_RESPONSE" });
}

function onlyKeys(value: Record<string, unknown>, keys: readonly string[]) {
  if (Object.keys(value).some((key) => !keys.includes(key))) invalidResponse();
}

function string(value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): value is string {
  return typeof value === "string" && value.length >= min && value.length <= max;
}

function integer(value: unknown, min = Number.MIN_SAFE_INTEGER, max = Number.MAX_SAFE_INTEGER): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= min && value <= max;
}

function finite(value: unknown, min = -Number.MAX_VALUE, max = Number.MAX_VALUE): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= min && value <= max;
}

function utc(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value)) && /(?:Z|[+-]\d{2}:\d{2})$/.test(value);
}

function uuid(value: unknown): value is string {
  return typeof value === "string" && UUID_PATTERN.test(value);
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function scalar(value: unknown): value is string | number | boolean | null {
  return value === null || typeof value === "string" || typeof value === "boolean" || finite(value);
}

function decimalOrNull(value: unknown): value is string | null {
  return value === null || typeof value === "string" && DECIMAL.test(value);
}

function validateMeta(value: unknown, strict: boolean): Record<string, string> {
  const meta = object(value);
  if (!meta || Object.values(meta).some((item) => typeof item !== "string")) invalidResponse();
  if (strict && (!utc(meta.timestamp) || !string(meta.request_id, 1))) invalidResponse();
  return meta as Record<string, string>;
}

function validateEnvelope(value: unknown, strictMeta: boolean) {
  const envelope = object(value);
  if (!envelope || envelope.success !== true || typeof envelope.message !== "string") invalidResponse();
  validateMeta(envelope.meta, strictMeta);
  return envelope;
}

function validatePagination(value: unknown): PaginationData {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["page", "page_size", "total_records", "total_pages", "has_next", "has_prev"]);
  if (!integer(item.page, 1) || !integer(item.page_size, 1, 100) || !integer(item.total_records, 0)
    || !integer(item.total_pages, 0) || typeof item.has_next !== "boolean" || typeof item.has_prev !== "boolean") invalidResponse();
  if (item.total_pages === 0 && (item.total_records !== 0 || item.has_next || item.has_prev)) invalidResponse();
  return item as unknown as PaginationData;
}

function validateSummary(value: unknown): ValidationSummary {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["passed", "failed", "missing", "not_applicable"]);
  if (!integer(item.passed, 0) || !integer(item.failed, 0) || !integer(item.missing, 0) || !integer(item.not_applicable, 0)) invalidResponse();
  return item as unknown as ValidationSummary;
}

function validateBoundingBox(value: unknown): BoundingBox {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["version", "page_number", "x0", "y0", "x1", "y1", "rotation"]);
  if ((item.version !== undefined && item.version !== "bbox-v1") || !integer(item.page_number, 1)
    || !finite(item.x0, 0, 1) || !finite(item.y0, 0, 1) || !finite(item.x1, 0, 1) || !finite(item.y1, 0, 1)
    || item.x0 >= item.x1 || item.y0 >= item.y1
    || (item.rotation !== undefined && (!integer(item.rotation) || !ROTATIONS.has(item.rotation)))) invalidResponse();
  return item as unknown as BoundingBox;
}

function validateTableCell(value: unknown): TableCell {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["row", "column", "text", "row_span", "column_span", "source_element_id", "bounding_box"]);
  if (!integer(item.row, 0) || !integer(item.column, 0) || !string(item.text, 0, 4096)
    || (item.row_span !== undefined && !integer(item.row_span, 1))
    || (item.column_span !== undefined && !integer(item.column_span, 1))
    || (item.source_element_id !== undefined && item.source_element_id !== null && !string(item.source_element_id, 1, 128))) invalidResponse();
  if (item.bounding_box !== undefined && item.bounding_box !== null) validateBoundingBox(item.bounding_box);
  return item as unknown as TableCell;
}

function validateTableRow(value: unknown): TableRow {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["row_index", "cells"]);
  if (!integer(item.row_index, 0) || !Array.isArray(item.cells) || item.cells.length > 200) invalidResponse();
  return { row_index: item.row_index, cells: item.cells.map(validateTableCell) };
}

function validateStructuredTable(value: unknown): StructuredTable {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["version", "headers", "rows"]);
  if ((item.version !== undefined && item.version !== "table-v1") || !Array.isArray(item.headers) || item.headers.length > 200
    || item.headers.some((header) => !string(header, 0, 4096)) || !Array.isArray(item.rows) || item.rows.length > 2000) invalidResponse();
  return { version: item.version as "table-v1" | undefined, headers: item.headers as string[], rows: item.rows.map(validateTableRow) };
}

function validateLineItem(value: unknown): ReviewLineItem {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["line_item_id", "origin", "line_order", "description", "hs_code", "quantity", "unit_price", "tax_amount", "total_price"]);
  if (!uuid(item.line_item_id) || (item.origin !== "extracted" && item.origin !== "reviewer_added") || !integer(item.line_order, 1, 500)
    || !nullableString(item.description) || !nullableString(item.hs_code) || !decimalOrNull(item.quantity)
    || !decimalOrNull(item.unit_price) || !decimalOrNull(item.tax_amount) || !decimalOrNull(item.total_price)) invalidResponse();
  return item as unknown as ReviewLineItem;
}

function validateInvoice(value: unknown): ReviewInvoice {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["invoice_id", "invoice_number", "supplier_name", "supplier_tax_id", "buyer_name", "date_issued", "due_date", "currency", "subtotal", "tax_amount", "discount_amount", "grand_total", "is_math_valid", "line_items"]);
  if (!uuid(item.invoice_id) || !nullableString(item.invoice_number) || !nullableString(item.supplier_name)
    || !nullableString(item.supplier_tax_id) || !nullableString(item.buyer_name)
    || !(item.date_issued === null || typeof item.date_issued === "string" && DATE_ONLY.test(item.date_issued))
    || !(item.due_date === null || typeof item.due_date === "string" && DATE_ONLY.test(item.due_date))
    || !nullableString(item.currency) || !decimalOrNull(item.subtotal) || !decimalOrNull(item.tax_amount)
    || !decimalOrNull(item.discount_amount) || !decimalOrNull(item.grand_total)
    || typeof item.is_math_valid !== "boolean" || !Array.isArray(item.line_items)) invalidResponse();
  return { ...(item as unknown as ReviewInvoice), line_items: item.line_items.map(validateLineItem) };
}

function validateEvidenceSummary(value: unknown): EvidenceSummary {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["field_path", "source_page", "evidence_excerpt", "confidence_score", "validation_state"]);
  if (!string(item.field_path, 1, 255) || (item.source_page !== undefined && item.source_page !== null && !integer(item.source_page, 1))
    || (item.evidence_excerpt !== undefined && item.evidence_excerpt !== null && !string(item.evidence_excerpt, 0, 1000))
    || !finite(item.confidence_score, 0, 100) || !VALIDATION_STATES.has(item.validation_state as ValidationState)) invalidResponse();
  return item as unknown as EvidenceSummary;
}

function validateRuleResult(value: unknown): RuleResult {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["rule_id", "scope_key", "status", "observed_value", "expected_value", "difference", "epsilon", "message_code", "blocks_approval"]);
  if (!string(item.rule_id, 1, 64) || !string(item.scope_key, 1, 255) || !RULE_STATUSES.has(item.status as RuleStatus)
    || (item.observed_value !== undefined && !scalar(item.observed_value)) || (item.expected_value !== undefined && !scalar(item.expected_value))
    || (item.difference !== undefined && !decimalOrNull(item.difference)) || (item.epsilon !== undefined && !decimalOrNull(item.epsilon))
    || !string(item.message_code, 1, 100) || typeof item.blocks_approval !== "boolean") invalidResponse();
  return item as unknown as RuleResult;
}

function validateReport(value: unknown): ValidationReport {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["validation_version", "is_math_valid", "approval_eligible", "summary", "results", "warnings", "blocking_reasons"]);
  if ((item.validation_version !== undefined && item.validation_version !== "human-review-v1")
    || typeof item.is_math_valid !== "boolean" || typeof item.approval_eligible !== "boolean"
    || !Array.isArray(item.results) || (item.warnings !== undefined && (!Array.isArray(item.warnings) || item.warnings.some((entry) => typeof entry !== "string")))
    || (item.blocking_reasons !== undefined && (!Array.isArray(item.blocking_reasons) || item.blocking_reasons.some((entry) => typeof entry !== "string")))) invalidResponse();
  return {
    ...(item as unknown as ValidationReport),
    summary: validateSummary(item.summary),
    results: item.results.map(validateRuleResult),
  };
}

function validateSource(value: unknown): SourceView {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["url", "expires_at", "mime_type", "page_count"]);
  if (typeof item.url !== "string" || !isSafeSourceUrl(item.url) || !utc(item.expires_at)
    || !MIME_TYPES.has(item.mime_type as string)
    || (item.page_count !== undefined && item.page_count !== null && !integer(item.page_count, 1))) invalidResponse();
  return item as unknown as SourceView;
}

export function validateDocumentDetailEnvelope(value: unknown): DocumentDetailEnvelope {
  const envelope = validateEnvelope(value, true);
  onlyKeys(envelope, ["success", "data", "message", "meta"]);
  const item = object(envelope.data);
  if (!item) invalidResponse();
  onlyKeys(item, ["document_id", "file_name", "file_size_bytes", "mime_type", "doc_type", "status", "overall_confidence", "created_at", "updated_at", "job_id", "uploaded_by", "review_revision", "permitted_actions", "invoice", "extraction_validation", "field_evidence", "latest_review_validation", "source_view"]);
  if (!uuid(item.document_id) || !string(item.file_name, 1, 255) || UNSAFE_FILENAME.test(item.file_name)
    || !integer(item.file_size_bytes, 1, MAX_DOCUMENT_BYTES) || !MIME_TYPES.has(item.mime_type as string)
    || !DOCUMENT_TYPES.has(item.doc_type as DocumentType) || !DOCUMENT_STATUSES.has(item.status as DocumentStatus)
    || !(item.overall_confidence === null || finite(item.overall_confidence, 0, 100)) || !utc(item.created_at) || !utc(item.updated_at)
    || !uuid(item.job_id) || !(item.uploaded_by === null || uuid(item.uploaded_by))
    || !(item.review_revision === null || integer(item.review_revision, 0)) || !Array.isArray(item.permitted_actions)
    || item.permitted_actions.some((action) => !ACTIONS.has(action as UserAction)) || !Array.isArray(item.field_evidence)) invalidResponse();

  const detail: DocumentDetail = {
    ...(item as unknown as DocumentDetail),
    invoice: item.invoice === null ? null : validateInvoice(item.invoice),
    extraction_validation: item.extraction_validation === null ? null : validateSummary(item.extraction_validation),
    field_evidence: item.field_evidence.map(validateEvidenceSummary),
    latest_review_validation: item.latest_review_validation === null ? null : validateReport(item.latest_review_validation),
    source_view: validateSource(item.source_view),
  };
  return { success: true, data: detail, message: envelope.message as string, meta: validateMeta(envelope.meta, true) as { timestamp: string; request_id: string } };
}

function validateChunk(value: unknown): ChunkItem {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["chunk_id", "parent_chunk_id", "ordinal", "page_start", "page_end", "section", "chunk_type", "retrieval_role", "token_count", "raw_content", "structured_content", "summary", "source_element_ids", "bounding_boxes", "embedding_status", "has_embedding"]);
  if (!uuid(item.chunk_id) || !(item.parent_chunk_id === null || uuid(item.parent_chunk_id)) || !integer(item.ordinal, 0)
    || !integer(item.page_start, 1) || !integer(item.page_end, item.page_start as number) || !nullableString(item.section)
    || !CHUNK_TYPES.has(item.chunk_type as string) || !RETRIEVAL_ROLES.has(item.retrieval_role as string)
    || !integer(item.token_count, 1) || !string(item.raw_content, 1, 32768)
    || (item.summary !== undefined && item.summary !== null && !string(item.summary, 0, 4096))
    || !Array.isArray(item.source_element_ids) || item.source_element_ids.length > 256 || item.source_element_ids.some((entry) => typeof entry !== "string")
    || !Array.isArray(item.bounding_boxes) || item.bounding_boxes.length > 256 || !EMBEDDING_STATUSES.has(item.embedding_status as EmbeddingStatus)
    || typeof item.has_embedding !== "boolean" || item.has_embedding !== (item.embedding_status === "completed")) invalidResponse();
  return {
    ...(item as unknown as ChunkItem),
    structured_content: item.structured_content === null ? null : validateStructuredTable(item.structured_content),
    bounding_boxes: item.bounding_boxes.map(validateBoundingBox),
  };
}

export function validateChunkListEnvelope(value: unknown): ChunkListEnvelope {
  const envelope = validateEnvelope(value, false);
  onlyKeys(envelope, ["success", "data", "message", "meta", "pagination"]);
  if (!Array.isArray(envelope.data)) invalidResponse();
  return {
    success: true,
    data: envelope.data.map(validateChunk),
    message: envelope.message as string,
    meta: validateMeta(envelope.meta, false),
    pagination: validatePagination(envelope.pagination),
  };
}

function validateRun(value: unknown): ExtractionRunInfo {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["extraction_run_id", "status", "pipeline_version", "parser_name", "parser_version", "ocr_policy_version", "embedding_model", "embedding_revision", "embedding_dimension", "llm_provider", "llm_model", "prompt_version", "schema_version", "warning_codes", "started_at", "completed_at"]);
  if (!uuid(item.extraction_run_id) || item.status !== "completed" || !string(item.pipeline_version)
    || item.parser_name !== "docling" || !string(item.parser_version) || !string(item.ocr_policy_version)
    || item.embedding_model !== "sentence-transformers/all-MiniLM-L6-v2" || !string(item.embedding_revision)
    || item.embedding_dimension !== 384 || !string(item.llm_provider) || !string(item.llm_model)
    || !string(item.prompt_version) || item.schema_version !== "commercial-invoice-v1"
    || !Array.isArray(item.warning_codes) || item.warning_codes.length > 64 || item.warning_codes.some((entry) => typeof entry !== "string")
    || !utc(item.started_at) || !utc(item.completed_at)) invalidResponse();
  return item as unknown as ExtractionRunInfo;
}

function validateEvidenceItem(value: unknown): EvidenceItem {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["field_path", "source_value", "normalized_value", "primary_chunk_id", "source_page", "bounding_box", "evidence_excerpt", "retrieval_rank", "retrieval_score", "confidence_score", "confidence_reason_codes", "validation_state"]);
  if (!string(item.field_path, 1, 255) || !nullableString(item.source_value) || !scalar(item.normalized_value)
    || !(item.primary_chunk_id === null || uuid(item.primary_chunk_id)) || !(item.source_page === null || integer(item.source_page, 1))
    || !nullableString(item.evidence_excerpt) || !(item.retrieval_rank === null || integer(item.retrieval_rank, 1))
    || !(item.retrieval_score === null || finite(item.retrieval_score, -1, 1)) || !finite(item.confidence_score, 0, 100)
    || !Array.isArray(item.confidence_reason_codes) || item.confidence_reason_codes.length > 64 || item.confidence_reason_codes.some((entry) => typeof entry !== "string")
    || !VALIDATION_STATES.has(item.validation_state as ValidationState)) invalidResponse();
  if (item.bounding_box !== null) validateBoundingBox(item.bounding_box);
  return item as unknown as EvidenceItem;
}

function validateRuleSummary(value: unknown): ValidationRuleSummary {
  const item = object(value);
  if (!item) invalidResponse();
  onlyKeys(item, ["rule_id", "scope_key", "status", "message_code", "observed_value", "expected_value", "difference", "epsilon"]);
  if (!string(item.rule_id) || !string(item.scope_key) || !RULE_STATUSES.has(item.status as RuleStatus) || !string(item.message_code)
    || !scalar(item.observed_value) || !scalar(item.expected_value) || !decimalOrNull(item.difference) || !decimalOrNull(item.epsilon)) invalidResponse();
  return item as unknown as ValidationRuleSummary;
}

export function validateEvidenceResponse(value: unknown): EvidenceResponse {
  const envelope = validateEnvelope(value, false);
  onlyKeys(envelope, ["success", "data", "message", "meta", "pagination"]);
  const data = object(envelope.data);
  if (!data) invalidResponse();
  onlyKeys(data, ["extraction_run", "items", "validation_summary", "rule_results"]);
  if (!Array.isArray(data.items) || !Array.isArray(data.rule_results)) invalidResponse();
  const decoded: ExtractionEvidenceData = {
    extraction_run: validateRun(data.extraction_run),
    items: data.items.map(validateEvidenceItem),
    validation_summary: validateSummary(data.validation_summary),
    rule_results: data.rule_results.map(validateRuleSummary),
  };
  return {
    success: true,
    data: decoded,
    message: envelope.message as string,
    meta: validateMeta(envelope.meta, false),
    pagination: validatePagination(envelope.pagination),
  };
}

export async function readDocumentDetail(documentId: string, signal?: AbortSignal) {
  if (!UUID_PATTERN.test(documentId)) invalidResponse();
  const raw = await apiEnvelopeRequest<unknown>(`/api/v1/documents/${documentId}`, { signal });
  return validateDocumentDetailEnvelope(raw);
}

export async function readWorkbench(documentId: string, query: WorkbenchQuery, signal?: AbortSignal) {
  if (!UUID_PATTERN.test(documentId)) invalidResponse();
  const params = backendWorkbenchQuery(query);
  if (query.mode === "chunks") {
    const raw = await apiEnvelopeRequest<unknown>(`/api/v1/documents/${documentId}/chunks?${params}`, { signal });
    return validateChunkListEnvelope(raw);
  }
  const raw = await apiEnvelopeRequest<unknown>(`/api/v1/documents/${documentId}/extraction-evidence?${params}`, { signal });
  return validateEvidenceResponse(raw);
}

