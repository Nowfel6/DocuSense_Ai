import type {
  ChunkListEnvelope,
  DocumentDetailEnvelope,
  EvidenceResponse,
} from "@/features/document-detail-chunk-inspector/types";

import { fixtureDocumentId, fixtureJobId } from "./documents-list-upload-monitor";

const requestMeta = { timestamp: "2026-09-15T08:00:00Z", request_id: "req_detail_fixture" };
const chunkId = "33333333-3333-4333-8333-333333333333";

export const documentDetailFixture: DocumentDetailEnvelope = {
  success: true,
  message: "Document loaded.",
  meta: requestMeta,
  data: {
    document_id: fixtureDocumentId,
    job_id: fixtureJobId,
    file_name: "northstar-invoice-2026-0042.pdf",
    file_size_bytes: 2048,
    mime_type: "application/pdf",
    doc_type: "commercial_invoice",
    status: "pending_review",
    overall_confidence: 94.5,
    created_at: "2026-09-14T09:00:00Z",
    updated_at: "2026-09-15T07:59:00Z",
    uploaded_by: null,
    review_revision: 0,
    permitted_actions: ["save", "approve", "reject"],
    source_view: {
      url: "https://objects.example.invalid/document.pdf?signature=fixture-secret",
      expires_at: "2030-09-15T08:10:00Z",
      mime_type: "application/pdf",
      page_count: 2,
    },
    invoice: null,
    extraction_validation: { passed: 3, failed: 0, missing: 1, not_applicable: 0 },
    field_evidence: [{
      field_path: "invoice.grand_total",
      source_page: 2,
      evidence_excerpt: "Grand total USD 120.00",
      confidence_score: 96,
      validation_state: "valid",
    }],
    latest_review_validation: null,
  },
};

export const chunkListFixture: ChunkListEnvelope = {
  success: true,
  message: "Chunks loaded.",
  meta: requestMeta,
  pagination: { page: 1, page_size: 50, total_records: 1, total_pages: 1, has_next: false, has_prev: false },
  data: [{
    chunk_id: chunkId,
    parent_chunk_id: null,
    ordinal: 0,
    page_start: 1,
    page_end: 1,
    section: "Invoice header",
    chunk_type: "text",
    retrieval_role: "both",
    token_count: 42,
    raw_content: "Invoice number NS-0042",
    structured_content: null,
    summary: "Invoice header fields",
    source_element_ids: ["element-1"],
    bounding_boxes: [{ version: "bbox-v1", page_number: 1, x0: 0.1, y0: 0.1, x1: 0.8, y1: 0.2, rotation: 0 }],
    embedding_status: "completed",
    has_embedding: true,
  }],
};

export const evidenceFixture: EvidenceResponse = {
  success: true,
  message: "Evidence loaded.",
  meta: requestMeta,
  pagination: { page: 1, page_size: 50, total_records: 1, total_pages: 1, has_next: false, has_prev: false },
  data: {
    extraction_run: {
      extraction_run_id: "44444444-4444-4444-8444-444444444444",
      status: "completed",
      pipeline_version: "1.0.0",
      parser_name: "docling",
      parser_version: "2.0.0",
      ocr_policy_version: "ocr-v1",
      embedding_model: "sentence-transformers/all-MiniLM-L6-v2",
      embedding_revision: "main",
      embedding_dimension: 384,
      llm_provider: "fixture-provider",
      llm_model: "fixture-model",
      prompt_version: "invoice-v1",
      schema_version: "commercial-invoice-v1",
      warning_codes: [],
      started_at: "2026-09-15T07:50:00Z",
      completed_at: "2026-09-15T07:55:00Z",
    },
    items: [{
      field_path: "invoice.grand_total",
      source_value: "USD 120.00",
      normalized_value: "120.00",
      primary_chunk_id: chunkId,
      source_page: 2,
      bounding_box: { version: "bbox-v1", page_number: 2, x0: 0.5, y0: 0.7, x1: 0.9, y1: 0.8, rotation: 0 },
      evidence_excerpt: "Grand total USD 120.00",
      retrieval_rank: 1,
      retrieval_score: 0.91,
      confidence_score: 96,
      confidence_reason_codes: ["DIRECT_MATCH"],
      validation_state: "valid",
    }],
    validation_summary: { passed: 3, failed: 0, missing: 1, not_applicable: 0 },
    rule_results: [{
      rule_id: "invoice_total_math",
      scope_key: "invoice",
      status: "passed",
      message_code: "TOTAL_MATCHES",
      observed_value: "120.00",
      expected_value: "120.00",
      difference: "0.00",
      epsilon: "0.01",
    }],
  },
};
