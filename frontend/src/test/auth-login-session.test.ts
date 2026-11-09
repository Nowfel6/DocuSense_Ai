import { beforeEach, describe, expect, it, vi } from "vitest";

import { createLoginSession } from "@/features/auth-login/session-client";
import { authProfile, jsonResponse, loginSuccess } from "@/test/fixtures/auth-login";

describe("browser login session adapter", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("accepts only the browser-safe profile envelope", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(loginSuccess));
    await expect(createLoginSession({
      email: "operator@example.test",
      password: "correct password",
    })).resolves.toEqual({ user: authProfile, expiresIn: 3600 });
    expect(fetchSpy).toHaveBeenCalledWith("/api/session/login", expect.objectContaining({
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
    }));
    expect(JSON.stringify((fetchSpy.mock.calls[0]?.[1] as RequestInit).body)).not.toContain("access_token");
  });

  it("rejects an incomplete success response with a safe code and request ID", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({
      success: true,
      data: { user: { ...authProfile, organizationName: undefined }, expires_in: 3600 },
      request_id: "req_incomplete",
    }));
    await expect(createLoginSession({
      email: "operator@example.test",
      password: "correct password",
    })).rejects.toMatchObject({
      code: "AUTH_RESPONSE_INVALID",
      requestId: "req_incomplete",
    });
  });

  it("uses stable codes rather than rendering backend messages", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({
      success: false,
      error: { code: "RATE_LIMITED", message: "internal details" },
    }, 429, { "retry-after": "30" }));
    await expect(createLoginSession({
      email: "operator@example.test",
      password: "correct password",
    })).rejects.toMatchObject({
      code: "RATE_LIMITED",
      retryAfter: "30",
    });
  });
});
