export type DocumentType = "commercial_invoice" | "purchase_order" | "packing_list";

export type DocumentStatus =
  | "queued"
  | "partitioning"
  | "chunking"
  | "vectorizing"
  | "extracting"
  | "pending_review"
  | "approved"
  | "rejected"
  | "failed";

export type JobStatus = "queued" | "processing" | "completed" | "failed";
export type ProcessingStage = "upload" | "partitioning" | "chunking" | "vectorizing" | "extracting";
export type StageStatus = "pending" | "in_progress" | "completed" | "failed";

export interface ApiMeta {
  timestamp: string;
  request_id: string;
}

export interface FeatureEnvelope<T> {
  success: true;
  data: T;
  message: string;
  meta: ApiMeta;
}

export interface DocumentSummary {
  document_id: string;
  file_name: string;
  file_size_bytes: number;
  mime_type: "application/pdf" | "image/png" | "image/jpeg";
  doc_type: DocumentType;
  status: DocumentStatus;
  overall_confidence: number | null;
  created_at: string;
  updated_at: string;
}

export interface PaginationData {
  page: number;
  page_size: number;
  total_records: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface DocumentListEnvelope extends FeatureEnvelope<DocumentSummary[]> {
  pagination: PaginationData;
}

export interface UploadWarning {
  code: "LOW_IMAGE_RESOLUTION" | "DUPLICATE_FILE_DETECTED";
  message: string;
}

export interface UploadAccepted {
  document_id: string;
  job_id: string;
  file_name: string;
  file_size_bytes: number;
  status: "queued";
  status_url: string;
  warnings: UploadWarning[];
}

export interface ProcessingError {
  code: "PDF_ENCRYPTED_OR_CORRUPT" | "PROCESSING_UNAVAILABLE" | "PROCESSING_FAILED";
  message: string;
}

export interface DocumentProgress {
  document_id: string;
  job_id: string;
  status: DocumentStatus;
  job_status: JobStatus;
  current_stage: ProcessingStage;
  progress_percentage: number;
  stages: Record<ProcessingStage, StageStatus>;
  error: ProcessingError | null;
}

export interface DocumentListQuery {
  page: number;
  pageSize: 20 | 50 | 100;
  status?: DocumentStatus;
  documentType?: DocumentType;
  fromDate?: string;
  toDate?: string;
  sortBy: "created_at" | "updated_at" | "file_name";
  order: "asc" | "desc";
}
