import type { UserRole } from "@/lib/auth/session-types";

export type SearchDocumentStatus = "pending_review" | "approved" | "rejected";
export type SearchDocumentType = "commercial_invoice" | "purchase_order" | "packing_list";
export type SearchSort = "relevance" | "date_issued" | "grand_total" | "created_at";
export type SortOrder = "asc" | "desc";
export type ExportFormat = "csv" | "xlsx" | "json";
export type ExportStatus = "queued" | "processing" | "completed" | "failed" | "expired";
export type ExportStage = "accepted" | "generating" | "packaging" | "storing" | "completed";

export interface SearchDraft {
  query: string;
  document_statuses: SearchDocumentStatus[];
  document_type: "" | SearchDocumentType;
  supplier: string;
  currency: string;
  invoice_date_from: string;
  invoice_date_to: string;
  uploaded_from: string;
  uploaded_to: string;
  min_total: string;
  max_total: string;
  sort_by: SearchSort;
  order: SortOrder;
  page: number;
  page_size: 20 | 50 | 100;
}

export interface SearchRequest {
  query?: string;
  document_statuses?: SearchDocumentStatus[];
  document_type?: SearchDocumentType;
  supplier?: string;
  currency?: string;
  invoice_date_from?: string;
  invoice_date_to?: string;
  uploaded_from?: string;
  uploaded_to?: string;
  min_total?: string;
  max_total?: string;
  sort_by: SearchSort;
  order: SortOrder;
  page: number;
  page_size: number;
}

export interface SearchResult {
  document_id: string;
  file_name: string;
  document_type: SearchDocumentType;
  status: SearchDocumentStatus;
  created_at: string;
  invoice_id: string;
  invoice_number: string | null;
  supplier_name: string | null;
  date_issued: string | null;
  currency: string | null;
  grand_total: string | null;
  is_math_valid: boolean;
  review_revision: number;
  relevance_score: number | null;
  matching_excerpt: string | null;
  matching_chunk_id: string | null;
  matching_page_start: number | null;
  matching_page_end: number | null;
  export_eligible: boolean;
  document_url: string;
  review_url: string | null;
}

export interface Pagination {
  page: number;
  page_size: number;
  total_records: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface SearchEnvelope {
  success: true;
  data: SearchResult[];
  message: string;
  meta: { timestamp: string; request_id: string };
  pagination: Pagination;
}

export interface ExportResource {
  export_id: string;
  format: ExportFormat;
  mode: "synchronous" | "asynchronous";
  status: ExportStatus;
  progress_percentage: number;
  current_stage: ExportStage;
  selected_document_count: number;
  exported_document_count: number;
  row_count: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  artifact_expires_at: string | null;
  status_url: string;
  download_url: string | null;
  error_code?: string | null;
  error_message?: string | null;
}

export interface SearchUrlState {
  draft: SearchDraft;
  exportId: string | null;
  hasStructuredCriteria: boolean;
}

export interface SearchHubProps {
  role: UserRole;
  initialState: SearchUrlState;
}

export type FieldErrors = Partial<Record<keyof SearchDraft | "criteria", string>>;

export const EMPTY_SEARCH_DRAFT: SearchDraft = {
  query: "",
  document_statuses: [],
  document_type: "",
  supplier: "",
  currency: "",
  invoice_date_from: "",
  invoice_date_to: "",
  uploaded_from: "",
  uploaded_to: "",
  min_total: "",
  max_total: "",
  sort_by: "created_at",
  order: "desc",
  page: 1,
  page_size: 20,
};
