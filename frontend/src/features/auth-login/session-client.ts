import type { SessionProfile, UserRole } from "@/lib/auth/session-types";

const LOGIN_TIMEOUT_MS = 20_000;

export type LoginErrorCode =
  | "INVALID_REQUEST"
  | "INVALID_CREDENTIALS"
  | "INVALID_ORIGIN"
  | "REQUEST_TOO_LARGE"
  | "RATE_LIMITED"
  | "AUTH_CONTRACT_INVALID"
  | "AUTH_SERVICE_UNAVAILABLE"
  | "AUTH_RESPONSE_INVALID"
  | "SESSION_UNAVAILABLE"
  | "NETWORK_OFFLINE"
  | "UNKNOWN";

export class LoginError extends Error {
  constructor(
    public readonly code: LoginErrorCode,
    options: { requestId?: string; retryAfter?: string } = {},
  ) {
    super(code);
    this.name = "LoginError";
    this.requestId = options.requestId;
    this.retryAfter = options.retryAfter;
  }

  readonly requestId?: string;
  readonly retryAfter?: string;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function isRole(value: unknown): value is UserRole {
  return value === "admin" || value === "operator" || value === "viewer";
}

function readProfile(value: unknown): SessionProfile | null {
  const profile = asRecord(value);
  if (
    typeof profile?.userId !== "string" ||
    typeof profile.email !== "string" ||
    typeof profile.displayName !== "string" ||
    !isRole(profile.role) ||
    typeof profile.organizationId !== "string" ||
    typeof profile.organizationName !== "string"
  ) return null;
  return profile as unknown as SessionProfile;
}

function knownCode(value: unknown): LoginErrorCode {
  const allowed: LoginErrorCode[] = [
    "INVALID_REQUEST",
    "INVALID_CREDENTIALS",
    "INVALID_ORIGIN",
    "REQUEST_TOO_LARGE",
    "RATE_LIMITED",
    "AUTH_CONTRACT_INVALID",
    "AUTH_SERVICE_UNAVAILABLE",
    "AUTH_RESPONSE_INVALID",
    "SESSION_UNAVAILABLE",
  ];
  return typeof value === "string" && allowed.includes(value as LoginErrorCode)
    ? value as LoginErrorCode
    : "UNKNOWN";
}

export async function createLoginSession(
  credentials: { email: string; password: string },
  externalSignal?: AbortSignal,
): Promise<{ user: SessionProfile; expiresIn: number }> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort("timeout"), LOGIN_TIMEOUT_MS);
  const abortFromExternal = () => controller.abort("navigation");
  externalSignal?.addEventListener("abort", abortFromExternal, { once: true });

  try {
    const response = await fetch("/api/session/login", {
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify(credentials),
      signal: controller.signal,
    });
    const payload = asRecord(await response.json().catch(() => null));
    const requestId = typeof payload?.request_id === "string"
      ? payload.request_id
      : response.headers.get("x-request-id") ?? undefined;

    if (!response.ok || payload?.success !== true) {
      const error = asRecord(payload?.error);
      throw new LoginError(knownCode(error?.code), {
        requestId,
        retryAfter: response.headers.get("retry-after") ?? undefined,
      });
    }

    const data = asRecord(payload.data);
    const user = readProfile(data?.user);
    const expiresIn = data?.expires_in;
    if (!user || typeof expiresIn !== "number" || !Number.isFinite(expiresIn) || expiresIn <= 0) {
      throw new LoginError("AUTH_RESPONSE_INVALID", { requestId });
    }
    return { user, expiresIn };
  } catch (error) {
    if (error instanceof LoginError) throw error;
    if (controller.signal.reason === "navigation") throw error;
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      throw new LoginError("NETWORK_OFFLINE");
    }
    throw new LoginError("AUTH_SERVICE_UNAVAILABLE");
  } finally {
    window.clearTimeout(timeout);
    externalSignal?.removeEventListener("abort", abortFromExternal);
  }
}
