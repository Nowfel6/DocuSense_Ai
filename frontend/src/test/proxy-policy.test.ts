import { describe, expect, it } from "vitest";

import {
  DEFAULT_JSON_BODY_BYTES,
  PROXY_RULES,
  REVIEW_JSON_BODY_BYTES,
  UPLOAD_BODY_BYTES,
  maxBodyBytesFor,
  proxyRuleFor,
  safeApiPath,
} from "@/lib/api/proxy-policy";

const allowedOperations = [
  ["POST", "/api/v1/documents/upload"],
  ["GET", "/api/v1/documents/doc_fixture/status"],
  ["GET", "/api/v1/documents"],
  ["GET", "/api/v1/documents/doc_fixture/chunks"],
  ["GET", "/api/v1/documents/doc_fixture/extraction-evidence"],
  ["POST", "/api/v1/documents/search"],
  ["GET", "/api/v1/documents/export"],
  ["POST", "/api/v1/exports"],
  ["GET", "/api/v1/exports/export_fixture/download"],
  ["GET", "/api/v1/exports/export_fixture"],
  ["GET", "/api/v1/analytics/dashboard"],
  ["GET", "/api/v1/activity-events"],
  ["POST", "/api/v1/documents/doc_fixture/review-validations"],
  ["PUT", "/api/v1/documents/doc_fixture/review"],
  ["GET", "/api/v1/documents/doc_fixture/audit-logs"],
  ["GET", "/api/v1/documents/doc_fixture"],
] as const;

describe("backend proxy policy", () => {
  it("contains exactly the 16 approved proxy operations", () => {
    expect(PROXY_RULES).toHaveLength(16);
    for (const [method, path] of allowedOperations) {
      expect(proxyRuleFor(method, path), `${method} ${path}`).not.toBeNull();
    }
  });

  it.each([
    ["POST", "/api/v1/auth/api-keys"],
    ["POST", "/api/v1/auth/login"],
    ["DELETE", "/api/v1/documents/doc_fixture"],
    ["GET", "/internal/health"],
  ])("denies %s %s", (method, path) => {
    expect(proxyRuleFor(method, path)).toBeNull();
  });

  it("rejects traversal and encodes valid dynamic segments", () => {
    expect(safeApiPath(["api", "v1", "documents", ".."])).toBeNull();
    expect(safeApiPath(["api", "v1", "documents", "a/b"])).toBeNull();
    expect(safeApiPath(["api", "v1", "documents", "doc fixture"])).toBe(
      "/api/v1/documents/doc%20fixture",
    );
  });

  it("uses the backend-aligned 20 MiB review cap without broadening other operations", () => {
    expect(maxBodyBytesFor(proxyRuleFor("POST", "/api/v1/documents/doc_fixture/review-validations")!)).toBe(REVIEW_JSON_BODY_BYTES);
    expect(maxBodyBytesFor(proxyRuleFor("PUT", "/api/v1/documents/doc_fixture/review")!)).toBe(REVIEW_JSON_BODY_BYTES);
    expect(maxBodyBytesFor(proxyRuleFor("GET", "/api/v1/documents/doc_fixture")!)).toBe(DEFAULT_JSON_BODY_BYTES);
    expect(maxBodyBytesFor(proxyRuleFor("POST", "/api/v1/documents/upload")!)).toBe(UPLOAD_BODY_BYTES);
  });
});
