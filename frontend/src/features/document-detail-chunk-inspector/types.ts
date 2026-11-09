import type {
  DocumentSummary,
  FeatureEnvelope,
  PaginationData,
} from "@/features/documents-list-upload-monitor/types";

export type UserAction = "save" | "approve" | "reject" | "reopen";
export type ValidationState = "valid" | "invalid" | "missing" | "ambiguous" | "unsupported";
export type RuleStatus = "passed" | "failed" | "missing" | "not_applicable";
export type ChunkType = "text" | "table" | "header" | "list" | "image" | "unknown";
export type RetrievalRole = "parent" | "child" | "both";
export type EmbeddingStatus = "pending" | "completed" | "failed" | "not_required";

export interface SourceView {
  url: string;
  expires_at: string;
  mime_type: "application/pdf" | "image/png" | "image/jpeg";
  page_count?: number | null;
}

export interface ValidationSummary {
  passed: number;
  failed: number;
  missing: number;
  not_applicable: number;
}

export interface RuleResult {
  rule_id: string;
  scope_key: string;
  status: RuleStatus;
  observed_value?: string | number | boolean | null;
  expected_value?: string | number | boolean | null;
  difference?: string | null;
  epsilon?: string | null;
  message_code: string;
  blocks_approval: boolean;
}

export interface ValidationReport {
  validation_version?: "human-review-v1";
  is_math_valid: boolean;
  approval_eligible: boolean;
  summary: ValidationSummary;
  results: RuleResult[];
  warnings?: string[];
  blocking_reasons?: string[];
}

export interface ReviewLineItem {
  line_item_id: string;
  origin: "extracted" | "reviewer_added";
  line_order: number;
  description: string | null;
  hs_code: string | null;
  quantity: string | null;
  unit_price: string | null;
  tax_amount: string | null;
  total_price: string | null;
}

export interface ReviewInvoice {
  invoice_id: string;
  invoice_number: string | null;
  supplier_name: string | null;
  supplier_tax_id: string | null;
  buyer_name: string | null;
  date_issued: string | null;
  due_date: string | null;
  currency: string | null;
  subtotal: string | null;
  tax_amount: string | null;
  discount_amount: string | null;
  grand_total: string | null;
  is_math_valid: boolean;
  line_items: ReviewLineItem[];
}

export interface EvidenceSummary {
  field_path: string;
  source_page?: number | null;
  evidence_excerpt?: string | null;
  confidence_score: number;
  validation_state: ValidationState;
}

export interface DocumentDetail extends DocumentSummary {
  job_id: string;
  uploaded_by: string | null;
  review_revision: number | null;
  permitted_actions: UserAction[];
  invoice: ReviewInvoice | null;
  extraction_validation: ValidationSummary | null;
  field_evidence: EvidenceSummary[];
  latest_review_validation: ValidationReport | null;
  source_view: SourceView;
}

export type DocumentDetailEnvelope = FeatureEnvelope<DocumentDetail>;

export interface BoundingBox {
  version?: "bbox-v1";
  page_number: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  rotation?: 0 | 90 | 180 | 270;
}

export interface TableCell {
  row: number;
  column: number;
  text: string;
  row_span?: number;
  column_span?: number;
  source_element_id?: string | null;
  bounding_box?: BoundingBox | null;
}

export interface TableRow {
  row_index: number;
  cells: TableCell[];
}

export interface StructuredTable {
  version?: "table-v1";
  headers: string[];
  rows: TableRow[];
}

export interface ChunkItem {
  chunk_id: string;
  parent_chunk_id: string | null;
  ordinal: number;
  page_start: number;
  page_end: number;
  section: string | null;
  chunk_type: ChunkType;
  retrieval_role: RetrievalRole;
  token_count: number;
  raw_content: string;
  structured_content: StructuredTable | null;
  summary?: string | null;
  source_element_ids: string[];
  bounding_boxes: BoundingBox[];
  embedding_status: EmbeddingStatus;
  has_embedding: boolean;
}

export interface ChunkListEnvelope {
  success: true;
  data: ChunkItem[];
  message: string;
  meta: Record<string, string>;
  pagination: PaginationData;
}

export interface ExtractionRunInfo {
  extraction_run_id: string;
  status: "completed";
  pipeline_version: string;
  parser_name: "docling";
  parser_version: string;
  ocr_policy_version: string;
  embedding_model: "sentence-transformers/all-MiniLM-L6-v2";
  embedding_revision: string;
  embedding_dimension: 384;
  llm_provider: string;
  llm_model: string;
  prompt_version: string;
  schema_version: "commercial-invoice-v1";
  warning_codes: string[];
  started_at: string;
  completed_at: string;
}

export interface EvidenceItem {
  field_path: string;
  source_value: string | null;
  normalized_value: string | number | boolean | null;
  primary_chunk_id: string | null;
  source_page: number | null;
  bounding_box: BoundingBox | null;
  evidence_excerpt: string | null;
  retrieval_rank: number | null;
  retrieval_score: number | null;
  confidence_score: number;
  confidence_reason_codes: string[];
  validation_state: ValidationState;
}

export interface ValidationRuleSummary {
  rule_id: string;
  scope_key: string;
  status: RuleStatus;
  message_code: string;
  observed_value: string | number | boolean | null;
  expected_value: string | number | boolean | null;
  difference: string | null;
  epsilon: string | null;
}

export interface ExtractionEvidenceData {
  extraction_run: ExtractionRunInfo;
  items: EvidenceItem[];
  validation_summary: ValidationSummary;
  rule_results: ValidationRuleSummary[];
}

export interface EvidenceResponse {
  success: true;
  data: ExtractionEvidenceData;
  message: string;
  meta: Record<string, string>;
  pagination: PaginationData;
}

export type WorkbenchMode = "chunks" | "evidence";

export interface ChunkQuery {
  mode: "chunks";
  page: number;
  pageSize: 20 | 50 | 100;
  chunkType?: ChunkType;
  pageNumber?: number;
  retrievalRole?: RetrievalRole;
  section?: string;
  order: "asc" | "desc";
}

export interface EvidenceQuery {
  mode: "evidence";
  page: number;
  pageSize: 20 | 50 | 100;
  fieldPath?: string;
  validationState?: ValidationState;
  minConfidence?: string;
}

export type WorkbenchQuery = ChunkQuery | EvidenceQuery;
export type WorkbenchEnvelope = ChunkListEnvelope | EvidenceResponse;

export type SelectedWorkbenchItem =
  | { mode: "chunks"; item: ChunkItem }
  | { mode: "evidence"; item: EvidenceItem };

