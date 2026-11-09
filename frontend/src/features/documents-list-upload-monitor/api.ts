import { apiEnvelopeRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

import { MAX_DOCUMENT_BYTES } from "./capabilities";
import { backendDocumentQuery } from "./list-query";
import type {
  DocumentListEnvelope,
  DocumentListQuery,
  DocumentProgress,
  DocumentStatus,
  DocumentSummary,
  DocumentType,
  FeatureEnvelope,
  JobStatus,
  ProcessingStage,
  StageStatus,
  UploadAccepted,
} from "./types";

// 8-4-4-4-12 hex shape. We intentionally do NOT enforce the RFC 4122 version
// (1-5) or variant ([89ab]) nibble, because seed/sentinel IDs (e.g. the
// deterministic `22222222-2222-2222-2222-222222222222` admin user) use the
// 8-4-4-4-12 shape without a strict variant nibble, and PostgreSQL's
// `gen_random_uuid()` (v4) is still accepted because the hex block sizes
// are unchanged.
export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DOCUMENT_STATUS = new Set<DocumentStatus>(["queued", "partitioning", "chunking", "vectorizing", "extracting", "pending_review", "approved", "rejected", "failed"]);
const DOCUMENT_TYPE = new Set<DocumentType>(["commercial_invoice", "purchase_order", "packing_list"]);
const JOB_STATUS = new Set<JobStatus>(["queued", "processing", "completed", "failed"]);
const STAGES: ProcessingStage[] = ["upload", "partitioning", "chunking", "vectorizing", "extracting"];
const STAGE_STATUS = new Set<StageStatus>(["pending", "in_progress", "completed", "failed"]);
const MIME = new Set(["application/pdf", "image/png", "image/jpeg"]);

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function finiteInteger(value: unknown, min: number, max = Number.MAX_SAFE_INTEGER): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= min && value <= max;
}

function utc(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value)) && /(?:Z|[+-]\d{2}:\d{2})$/.test(value);
}

function invalidResponse(): never {
  throw new ApiError("The service returned an unexpected response.", { code: "INVALID_API_RESPONSE" });
}

function validateBaseEnvelope(value: unknown) {
  const envelope = record(value);
  const meta = record(envelope?.meta);
  if (envelope?.success !== true || typeof envelope.message !== "string" || !meta
    || !utc(meta.timestamp) || typeof meta.request_id !== "string" || !meta.request_id.trim()) invalidResponse();
  return envelope;
}

function validateDocument(value: unknown): DocumentSummary {
  const item = record(value);
  if (!item || typeof item.document_id !== "string" || !UUID_PATTERN.test(item.document_id)
    || typeof item.file_name !== "string" || !item.file_name
    || !finiteInteger(item.file_size_bytes, 1, MAX_DOCUMENT_BYTES)
    || typeof item.mime_type !== "string" || !MIME.has(item.mime_type)
    || typeof item.doc_type !== "string" || !DOCUMENT_TYPE.has(item.doc_type as DocumentType)
    || typeof item.status !== "string" || !DOCUMENT_STATUS.has(item.status as DocumentStatus)
    || !(item.overall_confidence === null || typeof item.overall_confidence === "number" && Number.isFinite(item.overall_confidence) && item.overall_confidence >= 0 && item.overall_confidence <= 100)
    || !utc(item.created_at) || !utc(item.updated_at)) invalidResponse();
  return item as unknown as DocumentSummary;
}

export function validateDocumentListEnvelope(value: unknown): DocumentListEnvelope {
  const envelope = validateBaseEnvelope(value);
  const pagination = record(envelope.pagination);
  if (!Array.isArray(envelope.data) || !pagination
    || !finiteInteger(pagination.page, 1) || !finiteInteger(pagination.page_size, 1, 100)
    || !finiteInteger(pagination.total_records, 0) || !finiteInteger(pagination.total_pages, 0)
    || typeof pagination.has_next !== "boolean" || typeof pagination.has_prev !== "boolean") invalidResponse();
  const data = envelope.data.map(validateDocument);
  return { ...envelope, data } as unknown as DocumentListEnvelope;
}

export function validateUploadEnvelope(value: unknown): FeatureEnvelope<UploadAccepted> {
  const envelope = validateBaseEnvelope(value);
  const data = record(envelope.data);
  if (!data || typeof data.document_id !== "string" || !UUID_PATTERN.test(data.document_id)
    || typeof data.job_id !== "string" || !UUID_PATTERN.test(data.job_id)
    || typeof data.file_name !== "string" || !data.file_name
    || !finiteInteger(data.file_size_bytes, 1, MAX_DOCUMENT_BYTES) || data.status !== "queued"
    || data.status_url !== `/api/v1/documents/${data.document_id}/status` || !Array.isArray(data.warnings)) invalidResponse();
  for (const warning of data.warnings) {
    const item = record(warning);
    if (!item || (item.code !== "LOW_IMAGE_RESOLUTION" && item.code !== "DUPLICATE_FILE_DETECTED") || typeof item.message !== "string") invalidResponse();
  }
  return envelope as unknown as FeatureEnvelope<UploadAccepted>;
}

export function validateProgressEnvelope(value: unknown, expectedDocumentId: string): FeatureEnvelope<DocumentProgress> {
  const envelope = validateBaseEnvelope(value);
  const data = record(envelope.data);
  const stages = record(data?.stages);
  const error = data?.error === null ? null : record(data?.error);
  if (!data || data.document_id !== expectedDocumentId || !UUID_PATTERN.test(expectedDocumentId)
    || typeof data.job_id !== "string" || !UUID_PATTERN.test(data.job_id)
    || typeof data.status !== "string" || !DOCUMENT_STATUS.has(data.status as DocumentStatus)
    || typeof data.job_status !== "string" || !JOB_STATUS.has(data.job_status as JobStatus)
    || typeof data.current_stage !== "string" || !STAGES.includes(data.current_stage as ProcessingStage)
    || !finiteInteger(data.progress_percentage, 0, 100) || !stages || Object.keys(stages).length !== STAGES.length
    || STAGES.some((stage) => !STAGE_STATUS.has(stages[stage] as StageStatus))
    || (error !== null && (!(new Set(["PDF_ENCRYPTED_OR_CORRUPT", "PROCESSING_UNAVAILABLE", "PROCESSING_FAILED"])).has(error.code as string) || typeof error.message !== "string"))) invalidResponse();
  return envelope as unknown as FeatureEnvelope<DocumentProgress>;
}

export async function listDocuments(query: DocumentListQuery, signal?: AbortSignal) {
  const raw = await apiEnvelopeRequest<unknown>(`/api/v1/documents?${backendDocumentQuery(query)}` as `/api/v1/${string}`, { signal });
  return validateDocumentListEnvelope(raw);
}

export async function readDocumentProgress(documentId: string, signal?: AbortSignal) {
  if (!UUID_PATTERN.test(documentId)) invalidResponse();
  const raw = await apiEnvelopeRequest<unknown>(`/api/v1/documents/${documentId}/status`, { signal });
  return validateProgressEnvelope(raw, documentId);
}
