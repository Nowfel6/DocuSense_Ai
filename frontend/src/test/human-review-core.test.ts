import { describe, expect, it } from "vitest";

import { breadcrumbsForPathname } from "@/components/shell/navigation";
import { candidateHash, draftFromPreview, serializeDraft, validateDraft } from "@/features/human-review-studio/candidate";
import { validatePreviewEnvelope } from "@/features/human-review-studio/api";
import type { ReviewDraft } from "@/features/human-review-studio/types";
import { safeReturnPath } from "@/lib/auth/return-path";

const documentId = "11111111-1111-4111-8111-111111111111";
const lineId = "22222222-2222-4222-8222-222222222222";

function draft(): ReviewDraft {
  return {
    expected_review_revision: 3,
    invoice: {
      invoice_number: " INV-42 ",
      supplier_name: "Supplier",
      supplier_tax_id: null,
      buyer_name: "Buyer",
      date_issued: "2026-09-15",
      due_date: "2026-10-15",
      currency: "usd",
      subtotal: "100.00",
      tax_amount: "5.00",
      discount_amount: "0.00",
      grand_total: "105.00",
    },
    line_items: [{
      key: lineId,
      line_item_id: lineId,
      client_correlation_key: null,
      description: "Service",
      hs_code: null,
      quantity: "1.0000",
      unit_price: "100.0000",
      tax_amount: "5.00",
      total_price: "105.00",
      line_order: 1,
    }],
  };
}

function previewEnvelope() {
  const candidate = serializeDraft(draft());
  return {
    success: true,
    data: {
      review_revision: 3,
      invoice: candidate.invoice,
      line_items: candidate.line_items.map((line) => ({ ...line, origin: "extracted", calculated_total_price: "105.00" })),
      calculated_subtotal: "100.00",
      calculated_grand_total: "105.00",
      validation: {
        validation_version: "human-review-v1",
        is_math_valid: true,
        approval_eligible: true,
        summary: { passed: 2, failed: 0, missing: 0, not_applicable: 0 },
        results: [{ rule_id: "total", scope_key: "invoice.grand_total", status: "passed", message_code: "invoice_total_match", blocks_approval: false }],
        warnings: [],
        blocking_reasons: [],
      },
    },
    message: "Preview complete",
    meta: { timestamp: "2026-09-15T09:00:00Z", request_id: "req-review-1" },
  };
}

describe("human review contract core", () => {
  it("serializes only decimal strings/null and contiguous line order", () => {
    const serialized = serializeDraft(draft());
    expect(serialized.invoice).toMatchObject({ invoice_number: "INV-42", currency: "USD", subtotal: "100.00" });
    expect(serialized.line_items[0]).toMatchObject({ quantity: "1.0000", unit_price: "100.0000", line_order: 1 });
    expect(typeof serialized.invoice.grand_total).toBe("string");
  });

  it("rejects negative/over-precision decimals and impossible dates locally", () => {
    const value = draft();
    value.invoice.subtotal = "-1.00";
    value.invoice.date_issued = "2026-02-30";
    value.line_items[0].quantity = "1.00001";
    expect(validateDraft(value).errors).toMatchObject({
      "invoice.subtotal": expect.any(String),
      "invoice.date_issued": expect.any(String),
      [`line_items.${lineId}.quantity`]: expect.any(String),
    });
  });

  it("keeps persisted line identity through a normalized preview", () => {
    const decoded = validatePreviewEnvelope(previewEnvelope());
    const normalized = draftFromPreview(draft(), decoded.data);
    expect(normalized.line_items[0].key).toBe(lineId);
    expect(candidateHash(normalized)).toBe(candidateHash(draft()));
  });

  it("rejects unexpected preview fields instead of silently accepting drift", () => {
    const response = previewEnvelope() as ReturnType<typeof previewEnvelope> & { leaked?: string };
    response.leaked = "not allowed";
    expect(() => validatePreviewEnvelope(response)).toThrow("unexpected response");
  });

  it("allows the exact review return path but rejects query-bearing variants", () => {
    expect(safeReturnPath(`/documents/${documentId}/review`)).toBe(`/documents/${documentId}/review`);
    expect(safeReturnPath(`/documents/${documentId}/review?unsafe=1`)).toBe("/dashboard");
  });

  it("provides the contextual review breadcrumb", () => {
    expect(breadcrumbsForPathname(`/documents/${documentId}/review`)).toEqual([
      { label: "Documents", href: "/documents" },
      { label: "Document", href: `/documents/${documentId}` },
      { label: "Review" },
    ]);
  });
});
