import type { SessionProfile } from "@/lib/auth/session-types";

const SIGNUP_TIMEOUT_MS = 20_000;

export type SignupErrorCode =
  | "INVALID_REQUEST"
  | "EMAIL_TAKEN"
  | "INVALID_ORIGIN"
  | "REQUEST_TOO_LARGE"
  | "RATE_LIMITED"
  | "VALIDATION_ERROR"
  | "AUTH_CONTRACT_INVALID"
  | "AUTH_SERVICE_UNAVAILABLE"
  | "AUTH_RESPONSE_INVALID"
  | "SESSION_UNAVAILABLE"
  | "NETWORK_OFFLINE"
  | "UNKNOWN";

export class SignupError extends Error {
  constructor(
    public readonly code: SignupErrorCode,
    options: { requestId?: string; retryAfter?: string } = {},
  ) {
    super(code);
    this.name = "SignupError";
    this.requestId = options.requestId;
    this.retryAfter = options.retryAfter;
  }

  readonly requestId?: string;
  readonly retryAfter?: string;
}

export interface SignupPayload {
  full_name: string;
  organization_name: string;
  business_type: "importer" | "trading" | "logistics";
  country: string;
  email: string;
  password: string;
  agree_to_terms: true;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function isUserRole(value: unknown): value is SessionProfile["role"] {
  return value === "admin" || value === "operator" || value === "viewer";
}

function readProfile(value: unknown): SessionProfile | null {
  const profile = asRecord(value);
  if (
    typeof profile?.userId !== "string" ||
    typeof profile.email !== "string" ||
    typeof profile.displayName !== "string" ||
    !isUserRole(profile.role) ||
    typeof profile.organizationId !== "string" ||
    typeof profile.organizationName !== "string"
  ) return null;
  return profile as unknown as SessionProfile;
}

function knownCode(value: unknown): SignupErrorCode {
  const allowed: SignupErrorCode[] = [
    "INVALID_REQUEST",
    "EMAIL_TAKEN",
    "INVALID_ORIGIN",
    "REQUEST_TOO_LARGE",
    "RATE_LIMITED",
    "VALIDATION_ERROR",
    "AUTH_CONTRACT_INVALID",
    "AUTH_SERVICE_UNAVAILABLE",
    "AUTH_RESPONSE_INVALID",
    "SESSION_UNAVAILABLE",
  ];
  return typeof value === "string" && allowed.includes(value as SignupErrorCode)
    ? value as SignupErrorCode
    : "UNKNOWN";
}

export async function createSignupAccount(
  payload: SignupPayload,
  externalSignal?: AbortSignal,
): Promise<{ user: SessionProfile; expiresIn: number }> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort("timeout"), SIGNUP_TIMEOUT_MS);
  const abortFromExternal = () => controller.abort("navigation");
  externalSignal?.addEventListener("abort", abortFromExternal, { once: true });

  try {
    const response = await fetch("/api/session/signup", {
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const payloadRecord = asRecord(await response.json().catch(() => null));
    const requestId = typeof payloadRecord?.request_id === "string"
      ? payloadRecord.request_id
      : response.headers.get("x-request-id") ?? undefined;

    if (!response.ok || payloadRecord?.success !== true) {
      const error = asRecord(payloadRecord?.error);
      throw new SignupError(knownCode(error?.code), {
        requestId,
        retryAfter: response.headers.get("retry-after") ?? undefined,
      });
    }

    const data = asRecord(payloadRecord.data);
    const user = readProfile(data?.user);
    const expiresIn = data?.expires_in;
    if (!user || typeof expiresIn !== "number" || !Number.isFinite(expiresIn) || expiresIn <= 0) {
      throw new SignupError("AUTH_RESPONSE_INVALID", { requestId });
    }
    return { user, expiresIn };
  } catch (error) {
    if (error instanceof SignupError) throw error;
    if (controller.signal.reason === "navigation") throw error;
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      throw new SignupError("NETWORK_OFFLINE");
    }
    throw new SignupError("AUTH_SERVICE_UNAVAILABLE");
  } finally {
    window.clearTimeout(timeout);
    externalSignal?.removeEventListener("abort", abortFromExternal);
  }
}
