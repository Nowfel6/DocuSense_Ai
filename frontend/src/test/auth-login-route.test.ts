import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/session/login/route";

const writeSession = vi.hoisted(() => vi.fn());

vi.mock("@/lib/auth/session", () => ({
  isSessionConfigurationReady: () => true,
  writeSession,
}));

function loginRequest(body: unknown): Request {
  return new Request("https://app.example.test/api/session/login", {
    method: "POST",
    headers: {
      origin: "https://app.example.test",
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

function backendResponse(payload: unknown, status = 200, headers?: HeadersInit): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

describe("server login exchange", () => {
  beforeEach(() => {
    process.env.BACKEND_API_ORIGIN = "https://backend.example.test";
    writeSession.mockReset();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete process.env.BACKEND_API_ORIGIN;
  });

  it("maps concrete company fields and never returns the bearer token", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(backendResponse({
      success: true,
      data: {
        access_token: "server-only-token",
        user: {
          id: "user-1",
          email: "operator@example.test",
          full_name: "Example Operator",
          role: "operator",
          company_id: "company-1",
          company_name: "Example Workspace",
        },
      },
    }, 200, { "x-request-id": "req_success" }));

    const response = await POST(loginRequest({
      email: " operator@example.test ",
      password: "correct password",
    }));
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(JSON.stringify(payload)).not.toContain("server-only-token");
    expect(payload.data.user).toMatchObject({
      userId: "user-1",
      organizationId: "company-1",
      organizationName: "Example Workspace",
    });
    expect(writeSession).toHaveBeenCalledWith(
      "server-only-token",
      expect.objectContaining({ userId: "user-1", organizationId: "company-1" }),
      3600,
    );
  });

  it("normalizes rate limits and forwards a bounded Retry-After", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(backendResponse({
      detail: { code: "ANY_BACKEND_CODE", message: "sensitive" },
    }, 429, { "retry-after": "30", "x-request-id": "req_rate" }));

    const response = await POST(loginRequest({
      email: "operator@example.test",
      password: "correct password",
    }));
    const payload = await response.json();

    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("30");
    expect(payload.error.code).toBe("RATE_LIMITED");
    expect(JSON.stringify(payload)).not.toContain("sensitive");
  });

  it("rejects incomplete successful profiles without creating a session", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(backendResponse({
      success: true,
      data: {
        access_token: "server-only-token",
        user: {
          id: "user-1",
          email: "operator@example.test",
          full_name: "Example Operator",
          role: "operator",
          company_id: "company-1",
        },
      },
    }));

    const response = await POST(loginRequest({
      email: "operator@example.test",
      password: "correct password",
    }));
    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toMatchObject({
      error: { code: "AUTH_RESPONSE_INVALID" },
    });
    expect(writeSession).not.toHaveBeenCalled();
  });
});
