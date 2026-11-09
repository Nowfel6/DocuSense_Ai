import type { ReviewInvoice } from "@/features/document-detail-chunk-inspector/types";

import type {
  DraftValidation,
  InvoiceCandidate,
  PreviewData,
  ReviewCandidate,
  ReviewDraft,
  ReviewDraftLine,
} from "./types";

const CONTROL_OR_BIDI = /[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/;
const NONNEGATIVE_DECIMAL = /^(?:0|[1-9]\d*)(?:\.\d+)?$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const TEXT_LIMITS: Record<keyof Pick<InvoiceCandidate, "invoice_number" | "supplier_name" | "supplier_tax_id" | "buyer_name">, number> = {
  invoice_number: 100,
  supplier_name: 255,
  supplier_tax_id: 100,
  buyer_name: 255,
};

function optionalText(value: string | null): string | null {
  const normalized = value?.trim() ?? "";
  return normalized || null;
}

function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
}

function decimalError(value: string | null, integerDigits: number, fractionDigits: number): string | undefined {
  if (value === null || value.trim() === "") return undefined;
  const normalized = value.trim();
  if (!NONNEGATIVE_DECIMAL.test(normalized)) return "Enter a nonnegative decimal using digits and an optional decimal point.";
  const [integer, fraction = ""] = normalized.split(".");
  if (integer.length > integerDigits || fraction.length > fractionDigits) {
    return `Use at most ${integerDigits} digits before and ${fractionDigits} after the decimal point.`;
  }
}

export function draftFromInvoice(invoice: ReviewInvoice, reviewRevision: number): ReviewDraft {
  return {
    expected_review_revision: reviewRevision,
    invoice: {
      invoice_number: invoice.invoice_number,
      supplier_name: invoice.supplier_name,
      supplier_tax_id: invoice.supplier_tax_id,
      buyer_name: invoice.buyer_name,
      date_issued: invoice.date_issued,
      due_date: invoice.due_date,
      currency: invoice.currency,
      subtotal: invoice.subtotal,
      tax_amount: invoice.tax_amount,
      discount_amount: invoice.discount_amount,
      grand_total: invoice.grand_total,
    },
    line_items: invoice.line_items.map((line) => ({
      key: line.line_item_id,
      line_item_id: line.line_item_id,
      client_correlation_key: null,
      description: line.description,
      hs_code: line.hs_code,
      quantity: line.quantity,
      unit_price: line.unit_price,
      tax_amount: line.tax_amount,
      total_price: line.total_price,
      line_order: line.line_order,
    })),
  };
}

export function newDraftLine(): ReviewDraftLine {
  const key = `review-${crypto.randomUUID()}`;
  return {
    key,
    line_item_id: null,
    client_correlation_key: key,
    description: null,
    hs_code: null,
    quantity: null,
    unit_price: null,
    tax_amount: null,
    total_price: null,
    line_order: 1,
  };
}

export function serializeDraft(draft: ReviewDraft): ReviewCandidate {
  const decimal = (value: string | null) => optionalText(value);
  return {
    expected_review_revision: draft.expected_review_revision,
    invoice: {
      invoice_number: optionalText(draft.invoice.invoice_number),
      supplier_name: optionalText(draft.invoice.supplier_name),
      supplier_tax_id: optionalText(draft.invoice.supplier_tax_id),
      buyer_name: optionalText(draft.invoice.buyer_name),
      date_issued: optionalText(draft.invoice.date_issued),
      due_date: optionalText(draft.invoice.due_date),
      currency: optionalText(draft.invoice.currency)?.toUpperCase() ?? null,
      subtotal: decimal(draft.invoice.subtotal),
      tax_amount: decimal(draft.invoice.tax_amount),
      discount_amount: decimal(draft.invoice.discount_amount),
      grand_total: decimal(draft.invoice.grand_total),
    },
    line_items: draft.line_items.map((line, index) => ({
      line_item_id: line.line_item_id,
      client_correlation_key: line.client_correlation_key,
      description: optionalText(line.description),
      hs_code: optionalText(line.hs_code),
      quantity: decimal(line.quantity),
      unit_price: decimal(line.unit_price),
      tax_amount: decimal(line.tax_amount),
      total_price: decimal(line.total_price),
      line_order: index + 1,
    })),
  };
}

export function candidateHash(draft: ReviewDraft): string {
  return JSON.stringify(serializeDraft(draft));
}

export function validateDraft(draft: ReviewDraft): DraftValidation {
  const errors: Record<string, string> = {};
  for (const [key, limit] of Object.entries(TEXT_LIMITS) as Array<[keyof typeof TEXT_LIMITS, number]>) {
    const value = draft.invoice[key];
    if (value && (value.length > limit || CONTROL_OR_BIDI.test(value))) errors[`invoice.${key}`] = `Use plain text up to ${limit} characters.`;
  }
  for (const key of ["date_issued", "due_date"] as const) {
    const value = draft.invoice[key]?.trim();
    if (value && !validDate(value)) errors[`invoice.${key}`] = "Enter a real calendar date in YYYY-MM-DD format.";
  }
  const currency = draft.invoice.currency?.trim();
  if (currency && !/^[A-Za-z]{3}$/.test(currency)) errors["invoice.currency"] = "Enter a three-letter currency code.";
  for (const key of ["subtotal", "tax_amount", "discount_amount", "grand_total"] as const) {
    const error = decimalError(draft.invoice[key], 12, 2);
    if (error) errors[`invoice.${key}`] = error;
  }
  if (draft.line_items.length > 500) errors.line_items = "A review can contain at most 500 line items.";
  draft.line_items.forEach((line, index) => {
    const base = `line_items.${line.key}`;
    if (line.line_item_id !== null && !UUID.test(line.line_item_id)) errors[`${base}.line_item_id`] = "The persisted line identity is invalid.";
    if (line.description && (line.description.length > 32768 || CONTROL_OR_BIDI.test(line.description))) errors[`${base}.description`] = "Use plain text up to 32,768 characters.";
    if (line.hs_code && (line.hs_code.length > 50 || CONTROL_OR_BIDI.test(line.hs_code))) errors[`${base}.hs_code`] = "Use plain text up to 50 characters.";
    for (const key of ["quantity", "unit_price"] as const) {
      const error = decimalError(line[key], key === "quantity" ? 14 : 10, 4);
      if (error) errors[`${base}.${key}`] = error;
    }
    for (const key of ["tax_amount", "total_price"] as const) {
      const error = decimalError(line[key], 12, 2);
      if (error) errors[`${base}.${key}`] = error;
    }
    if (line.line_order !== index + 1) errors[`${base}.line_order`] = "Line order is inconsistent.";
  });
  return { errors, firstPath: Object.keys(errors)[0] };
}

export function draftFromPreview(current: ReviewDraft, preview: PreviewData): ReviewDraft {
  return {
    expected_review_revision: preview.review_revision,
    invoice: preview.invoice,
    line_items: preview.line_items.map((line, index) => {
      const existing = current.line_items.find((item) =>
        line.line_item_id ? item.line_item_id === line.line_item_id : item.client_correlation_key === line.client_correlation_key,
      );
      return {
        key: existing?.key ?? line.line_item_id ?? line.client_correlation_key ?? `preview-${index + 1}`,
        line_item_id: line.line_item_id,
        client_correlation_key: line.client_correlation_key,
        description: line.description,
        hs_code: line.hs_code,
        quantity: line.quantity,
        unit_price: line.unit_price,
        tax_amount: line.tax_amount,
        total_price: line.total_price,
        line_order: index + 1,
      };
    }),
  };
}
