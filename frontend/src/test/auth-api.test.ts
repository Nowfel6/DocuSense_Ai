import { describe, expect, it } from "vitest";

import { ApiError, normalizeApiError } from "@/lib/api/errors";
import { safeReturnPath } from "@/lib/auth/return-path";
import { isSameOriginRequest } from "@/lib/auth/request-security";

describe("auth and API safety helpers", () => {
  it.each([
    ["https://evil.invalid/steal", "/dashboard"],
    ["//evil.invalid/steal", "/dashboard"],
    ["/login", "/dashboard"],
    ["/api/backend/api/v1/documents", "/dashboard"],
    ["/documents?page=2", "/documents?page=2"],
    ["/documents?unknown=value&page=2", "/documents?page=2"],
    ["/documents/upload?document=not-a-uuid", "/documents/upload"],
    ["/dashboard?page=2", "/dashboard?page=2"],
  ])("normalizes return path %s", (candidate, expected) => {
    expect(safeReturnPath(candidate)).toBe(expected);
  });

  it("requires the request origin to match", () => {
    const accepted = new Request("https://app.example.invalid/api/session/logout", { headers: { origin: "https://app.example.invalid" } });
    const rejected = new Request("https://app.example.invalid/api/session/logout", { headers: { origin: "https://evil.example.invalid" } });
    expect(isSameOriginRequest(accepted)).toBe(true);
    expect(isSameOriginRequest(rejected)).toBe(false);
  });

  it("preserves already-normalized errors", () => {
    const error = new ApiError("Safe failure", { code: "SAFE", requestId: "req_fixture" });
    expect(normalizeApiError(error)).toBe(error);
  });
});
