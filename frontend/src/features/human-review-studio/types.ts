import type { PaginationData } from "@/features/documents-list-upload-monitor/types";
import type {
  ReviewInvoice,
  RuleResult,
  UserAction,
  ValidationReport,
} from "@/features/document-detail-chunk-inspector/types";

export interface InvoiceCandidate {
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
}

export interface LineItemCandidate {
  line_item_id: string | null;
  client_correlation_key: string | null;
  description: string | null;
  hs_code: string | null;
  quantity: string | null;
  unit_price: string | null;
  tax_amount: string | null;
  total_price: string | null;
  line_order: number;
}

export interface ReviewCandidate {
  invoice: InvoiceCandidate;
  line_items: LineItemCandidate[];
  expected_review_revision: number;
}

export interface ReviewDraftLine extends LineItemCandidate {
  key: string;
}

export interface ReviewDraft {
  invoice: InvoiceCandidate;
  line_items: ReviewDraftLine[];
  expected_review_revision: number;
}

export interface PreviewLineItem extends LineItemCandidate {
  origin: "extracted" | "reviewer_added";
  calculated_total_price: string | null;
}

export interface PreviewData {
  review_revision: number;
  invoice: InvoiceCandidate;
  line_items: PreviewLineItem[];
  calculated_subtotal: string | null;
  calculated_grand_total: string | null;
  validation: ValidationReport;
}

export interface MutationData {
  document_id: string;
  status: "pending_review" | "approved" | "rejected";
  review_revision: number;
  invoice: ReviewInvoice;
  latest_review_validation: ValidationReport | null;
  audit_event_id: string;
  permitted_actions: UserAction[];
}

export type MutationBody =
  | (ReviewCandidate & { action: "save" | "approve"; note: string | null })
  | { action: "reject" | "reopen"; expected_review_revision: number; reason: string };

export type AuditAction = "field_edited" | "approved" | "rejected" | "reopened";
export type AuditChangeValue = string | number | boolean | null | Record<string, string | number | boolean | null> | Array<string | number | boolean | null>;

export interface AuditChange {
  field_path: string;
  change_kind: "set" | "add" | "remove" | "reorder";
  old_value?: AuditChangeValue;
  new_value?: AuditChangeValue;
}

export interface AuditEvent {
  audit_event_id: string;
  actor_user_id: string;
  actor_display_name: string | null;
  action: AuditAction;
  from_status: "pending_review" | "approved" | "rejected";
  to_status: "pending_review" | "approved" | "rejected";
  review_revision: number;
  reason: string | null;
  note: string | null;
  request_id: string;
  created_at: string;
  changes: AuditChange[];
}

export interface ReviewEnvelope<T> {
  success: true;
  data: T;
  message: string;
  meta: { timestamp: string; request_id: string };
}

export interface AuditEnvelope extends ReviewEnvelope<AuditEvent[]> {
  pagination: PaginationData;
}

export interface DraftValidation {
  errors: Record<string, string>;
  firstPath?: string;
}

export interface CurrentPreview {
  data: PreviewData;
  candidateHash: string;
  receivedAt: number;
}

export type { RuleResult };
