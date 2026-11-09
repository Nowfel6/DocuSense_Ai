import { describe, expect, it } from "vitest";

import { validateDocumentFile, MAX_DOCUMENT_BYTES } from "@/features/documents-list-upload-monitor/capabilities";
import { validateDocumentListEnvelope, validateProgressEnvelope, validateUploadEnvelope } from "@/features/documents-list-upload-monitor/api";
import { backendDocumentQuery, normalizeDocumentQuery } from "@/features/documents-list-upload-monitor/list-query";
import { monitorRetryDelay } from "@/features/documents-list-upload-monitor/use-document-monitor";
import { apiErrorFromPayload } from "@/lib/api/client";
import { ApiError, parseRetryAfter } from "@/lib/api/errors";
import { safeReturnPath } from "@/lib/auth/return-path";

import { documentListFixture, fixtureDocumentId, progressFixture, uploadAcceptedFixture } from "./fixtures/documents-list-upload-monitor";

describe("documents contract-critical helpers", () => {
  it("normalizes unsupported, duplicate, reversed-date, and viewer status query values", () => {
    const invalid = normalizeDocumentQuery("page=2&page=3&supplier=x&from_date=2026-09-20&to_date=2026-09-10");
    expect(invalid).toMatchObject({ reset: true, canonical: "" });
    expect(normalizeDocumentQuery("status=approved&doc_type=packing_list", true)).toMatchObject({
      reset: true,
      canonical: "doc_type=packing_list",
    });
  });

  it("emits only exact backend query keys and explicit defaults", () => {
    const normalized = normalizeDocumentQuery("doc_type=purchase_order&sort_by=file_name&order=asc");
    expect(backendDocumentQuery(normalized.query)).toBe("doc_type=purchase_order&sort_by=file_name&order=asc&page=1&page_size=20");
  });

  it("validates full list, upload, and progress envelopes", () => {
    expect(validateDocumentListEnvelope(documentListFixture).pagination.total_records).toBe(1);
    expect(validateUploadEnvelope(uploadAcceptedFixture).data.document_id).toBe(fixtureDocumentId);
    expect(validateProgressEnvelope(progressFixture, fixtureDocumentId).data.current_stage).toBe("vectorizing");
    expect(() => validateUploadEnvelope({ ...uploadAcceptedFixture, data: { ...uploadAcceptedFixture.data, status_url: "https://evil.example/status" } })).toThrow("unexpected response");
  });

  it("rejects incomplete or inconsistent successful payloads", () => {
    expect(() => validateDocumentListEnvelope({ ...documentListFixture, pagination: undefined })).toThrow("unexpected response");
    expect(() => validateProgressEnvelope(progressFixture, "33333333-3333-4333-8333-333333333333")).toThrow("unexpected response");
  });

  it("enforces the inclusive file capability without duplicating server authority", () => {
    expect(validateDocumentFile(new File([new Uint8Array(MAX_DOCUMENT_BYTES)], "invoice.PDF", { type: "application/pdf" }))).toBeNull();
    expect(validateDocumentFile(new File([], "invoice.pdf", { type: "application/pdf" }))).toBe("Choose a file that is not empty.");
    expect(validateDocumentFile(new File(["x"], "invoice.exe", { type: "application/octet-stream" }))).toContain("PDF, PNG");
  });

  it("normalizes meta request IDs and bounded delta Retry-After values", () => {
    const error = apiErrorFromPayload({ success: false, error: { code: "RATE_LIMITED", message: "Wait." }, meta: { request_id: "req_meta" } }, 429, {
      get: (name) => name === "retry-after" ? "90" : null,
    });
    expect(error).toMatchObject({ code: "RATE_LIMITED", requestId: "req_meta", retryAfterSeconds: 30 });
    expect(parseRetryAfter("0")).toBe(1);
    expect(parseRetryAfter("Wed, 21 Oct 2026 07:28:00 GMT")).toBeUndefined();
  });

  it("uses bounded polling backoff and honors forwarded rate limits", () => {
    expect(monitorRetryDelay(new ApiError("offline", { code: "NETWORK_ERROR" }), 3)).toBe(16);
    expect(monitorRetryDelay(new ApiError("limited", { status: 429, retryAfterSeconds: 7 }), 0)).toBe(7);
    expect(monitorRetryDelay(new ApiError("missing", { status: 404 }), 0)).toBeNull();
  });

  it("preserves only released, validated document return paths", () => {
    expect(safeReturnPath("/documents?status=approved&page=2&secret=x")).toBe("/documents?page=2&status=approved");
    expect(safeReturnPath(`/documents/upload?document=${fixtureDocumentId}`)).toBe(`/documents/upload?document=${fixtureDocumentId}`);
    expect(safeReturnPath("//evil.example/documents")).toBe("/dashboard");
  });
});
