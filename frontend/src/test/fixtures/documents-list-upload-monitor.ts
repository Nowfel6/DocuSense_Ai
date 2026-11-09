import type { DocumentListEnvelope, DocumentProgress, FeatureEnvelope, UploadAccepted } from "@/features/documents-list-upload-monitor/types";

export const fixtureDocumentId = "11111111-1111-4111-8111-111111111111";
export const fixtureJobId = "22222222-2222-4222-8222-222222222222";

const meta = { timestamp: "2026-09-14T10:00:00Z", request_id: "req_documents_fixture" };

export const documentListFixture: DocumentListEnvelope = {
  success: true,
  message: "Documents loaded.",
  meta,
  data: [{
    document_id: fixtureDocumentId,
    file_name: "northstar-invoice-2026-0042.pdf",
    file_size_bytes: 2048,
    mime_type: "application/pdf",
    doc_type: "commercial_invoice",
    status: "partitioning",
    overall_confidence: null,
    created_at: "2026-09-14T09:00:00Z",
    updated_at: "2026-09-14T09:01:00Z",
  }],
  pagination: { page: 1, page_size: 20, total_records: 1, total_pages: 1, has_next: false, has_prev: false },
};

export const uploadAcceptedFixture: FeatureEnvelope<UploadAccepted> = {
  success: true,
  message: "Document accepted.",
  meta,
  data: {
    document_id: fixtureDocumentId,
    job_id: fixtureJobId,
    file_name: "northstar-invoice-2026-0042.pdf",
    file_size_bytes: 2048,
    status: "queued",
    status_url: `/api/v1/documents/${fixtureDocumentId}/status`,
    warnings: [],
  },
};

export const progressFixture: FeatureEnvelope<DocumentProgress> = {
  success: true,
  message: "Status loaded.",
  meta,
  data: {
    document_id: fixtureDocumentId,
    job_id: fixtureJobId,
    status: "vectorizing",
    job_status: "processing",
    current_stage: "vectorizing",
    progress_percentage: 60,
    stages: { upload: "completed", partitioning: "completed", chunking: "completed", vectorizing: "in_progress", extracting: "pending" },
    error: null,
  },
};
