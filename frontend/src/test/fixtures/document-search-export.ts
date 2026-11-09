import type { ExportResource, SearchEnvelope, SearchResult } from "@/features/document-search-export/types";

export const documentId = "11111111-1111-4111-8111-111111111111";
export const invoiceId = "22222222-2222-4222-8222-222222222222";
export const chunkId = "33333333-3333-4333-8333-333333333333";
export const exportId = "44444444-4444-4444-8444-444444444444";

export function searchResult(patch: Partial<SearchResult> = {}): SearchResult {
  return {
    document_id: documentId,
    file_name: "synthetic-invoice.pdf",
    document_type: "commercial_invoice",
    status: "approved",
    created_at: "2026-09-16T00:00:00Z",
    invoice_id: invoiceId,
    invoice_number: "INV-42",
    supplier_name: "Example Supplier",
    date_issued: "2026-09-15",
    currency: "USD",
    grand_total: "123456789012.34",
    is_math_valid: true,
    review_revision: 2,
    relevance_score: 0.875,
    matching_excerpt: "Synthetic matching text only.",
    matching_chunk_id: chunkId,
    matching_page_start: 1,
    matching_page_end: 1,
    export_eligible: true,
    document_url: `/documents/${documentId}`,
    review_url: `/documents/${documentId}/review`,
    ...patch,
  };
}

export function searchEnvelope(patch: Partial<SearchEnvelope> = {}): SearchEnvelope {
  return {
    success: true,
    data: [searchResult()],
    message: "Synthetic search completed.",
    meta: { timestamp: "2026-09-16T00:00:01Z", request_id: "fixture-search" },
    pagination: { page: 1, page_size: 20, total_records: 1, total_pages: 1, has_next: false, has_prev: false },
    ...patch,
  };
}

export function exportResource(patch: Partial<ExportResource> = {}): ExportResource {
  return {
    export_id: exportId,
    format: "csv",
    mode: "synchronous",
    status: "completed",
    progress_percentage: 100,
    current_stage: "completed",
    selected_document_count: 1,
    exported_document_count: 1,
    row_count: 2,
    created_at: "2026-09-16T00:00:00Z",
    started_at: "2026-09-16T00:00:01Z",
    completed_at: "2026-09-16T00:00:02Z",
    artifact_expires_at: "2026-09-23T00:00:02Z",
    status_url: `/api/v1/exports/${exportId}`,
    download_url: `/api/v1/exports/${exportId}/download`,
    ...patch,
  };
}

export function successEnvelope<T>(data: T) {
  return { success: true, data, message: "Synthetic success.", meta: { timestamp: "2026-09-16T00:00:01Z", request_id: "fixture-export" } };
}
