import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { validateExportEnvelope, validateSearchEnvelope, serializeSearch } from "@/features/document-search-export/api";
import { formatMoneyString } from "@/features/document-search-export/format";
import { canonicalSearchParams, parseSearchUrl } from "@/features/document-search-export/search-query";
import { EMPTY_SEARCH_DRAFT } from "@/features/document-search-export/types";
import { safeExportRedirectLocation } from "@/lib/api/proxy-policy";
import { safeReturnPath } from "@/lib/auth/return-path";

import { exportId, exportResource, searchEnvelope, successEnvelope } from "./fixtures/document-search-export";

describe("document search/export contract", () => {
  it("keeps the reviewed OpenAPI surface current", () => {
    const path = resolve(__dirname, "../../../docs/api/openapi.yaml");
    const schema = JSON.parse(readFileSync(path, "utf8"));
    expect(Object.keys(schema.paths)).toHaveLength(18);
    expect(Object.keys(schema.components.schemas)).toHaveLength(95);
    expect(schema.paths["/api/v1/documents/search"].post.requestBody).toBeTruthy();
    expect(Object.keys(schema.paths["/api/v1/exports"].post.responses).sort()).toContain("201");
    expect(Object.keys(schema.paths["/api/v1/exports"].post.responses).sort()).toContain("202");
    expect(schema.paths["/api/v1/exports/{export_id}/download"].get.responses["302"].headers.Location).toBeTruthy();
  });

  it("serializes exact strings and private semantic text only in the POST body", () => {
    const draft = { ...EMPTY_SEARCH_DRAFT, query: "  invoice steel  ", currency: "usd", min_total: "0.00", max_total: "123456789012.34", sort_by: "relevance" as const };
    const output = serializeSearch(draft);
    expect(output.errors).toEqual({});
    expect(output.request).toMatchObject({ query: "invoice steel", currency: "USD", min_total: "0.00", max_total: "123456789012.34" });
    expect(canonicalSearchParams(draft)).not.toContain("query");
  });

  it("rejects missing criteria and reversed exact-money ranges", () => {
    expect(serializeSearch(EMPTY_SEARCH_DRAFT).errors.criteria).toBeTruthy();
    const invalid = serializeSearch({ ...EMPTY_SEARCH_DRAFT, min_total: "10.01", max_total: "10.00" });
    expect(invalid.errors.max_total).toMatch(/below minimum/i);
  });

  it("canonicalizes only structured URL state and safe return paths", () => {
    const input = new URLSearchParams(`query=secret&status=approved&status=pending_review&page=2&export_id=${exportId}&unknown=x`);
    const state = parseSearchUrl(input);
    expect(state.draft.query).toBe("");
    expect(canonicalSearchParams(state.draft, state.exportId)).toBe(`status=pending_review&status=approved&page=2&export_id=${exportId}`);
    expect(safeReturnPath(`/documents/search?${input}`)).not.toContain("secret");
  });

  it("strictly decodes semantic results and rejects evidence in structured-only results", () => {
    expect(validateSearchEnvelope(searchEnvelope(), true).data[0].relevance_score).toBe(0.875);
    expect(() => validateSearchEnvelope(searchEnvelope(), false)).toThrow(/unexpected response/i);
  });

  it("enforces completed export invariants", () => {
    expect(validateExportEnvelope(successEnvelope(exportResource())).status).toBe("completed");
    expect(() => validateExportEnvelope(successEnvelope(exportResource({ progress_percentage: 99 })))).toThrow(/unexpected response/i);
  });

  it("allows only configured HTTPS signed redirect origins", () => {
    const path = `/api/v1/exports/${exportId}/download`;
    expect(safeExportRedirectLocation(path, 302, "https://storage.docusense.invalid/file?sig=redacted", "https://storage.docusense.invalid")).toContain("storage.docusense.invalid");
    expect(safeExportRedirectLocation(path, 302, "https://evil.invalid/file", "https://storage.docusense.invalid")).toBeNull();
    expect(safeExportRedirectLocation(path, 302, "http://storage.docusense.invalid/file", "https://storage.docusense.invalid")).toBeNull();
  });

  it("formats maximum money without binary floating-point conversion", () => {
    expect(formatMoneyString("123456789012.34", "USD")).toBe("USD 123,456,789,012.34");
    expect(formatMoneyString(null, "USD")).toBe("Not available");
  });
});
