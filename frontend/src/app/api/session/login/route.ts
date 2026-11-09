import { NextResponse } from "next/server";

import { isSameOriginRequest } from "@/lib/auth/request-security";
import { isSessionConfigurationReady, writeSession } from "@/lib/auth/session";
import type { SessionProfile, UserRole } from "@/lib/auth/session-types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_LOGIN_BODY_BYTES = 16 * 1024;
const BACKEND_TIMEOUT_MS = 15_000;

type SessionErrorCode =
  | "INVALID_REQUEST"
  | "INVALID_CREDENTIALS"
  | "INVALID_ORIGIN"
  | "REQUEST_TOO_LARGE"
  | "RATE_LIMITED"
  | "AUTH_CONTRACT_INVALID"
  | "AUTH_SERVICE_UNAVAILABLE"
  | "AUTH_RESPONSE_INVALID"
  | "SESSION_UNAVAILABLE";

function backendOrigin(): string | null {
  const candidate = process.env.BACKEND_API_ORIGIN;
  if (!candidate) return null;
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.origin : null;
  } catch {
    return null;
  }
}

function isRole(value: unknown): value is UserRole {
  return value === "admin" || value === "operator" || value === "viewer";
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function pickString(record: Record<string, unknown> | null, ...keys: string[]): string | null {
  for (const key of keys) {
    if (typeof record?.[key] === "string" && record[key]) return record[key] as string;
  }
  return null;
}

function readProfile(data: Record<string, unknown>): SessionProfile | null {
  const user = asRecord(data.user);
  const role = user?.role;
  if (!user || !isRole(role)) return null;

  const email = pickString(user, "email");
  const displayName = pickString(user, "full_name");
  const userId = pickString(user, "id");
  const organizationId = pickString(user, "company_id");
  const organizationName = pickString(user, "company_name");
  if (!email || !displayName || !userId || !organizationId || !organizationName) return null;
  return { email, displayName, userId, role, organizationId, organizationName };
}

function safeRetryAfter(value: string | null): string | null {
  if (!value) return null;
  if (/^\d{1,5}$/.test(value) && Number(value) <= 86_400) return value;
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return null;
  const remaining = timestamp - Date.now();
  return remaining >= 0 && remaining <= 86_400_000 ? new Date(timestamp).toUTCString() : null;
}

function errorResponse(
  code: SessionErrorCode,
  message: string,
  status: number,
  requestId?: string | null,
  retryAfter?: string | null,
) {
  const headers = new Headers();
  if (requestId) headers.set("x-request-id", requestId);
  if (retryAfter) headers.set("retry-after", retryAfter);
  return NextResponse.json({
    success: false,
    error: { code, message },
    ...(requestId ? { request_id: requestId } : {}),
  }, { status, headers });
}

export async function POST(request: Request) {
  if (!isSameOriginRequest(request)) {
    return errorResponse("INVALID_ORIGIN", "The request origin could not be verified.", 403);
  }
  if (!isSessionConfigurationReady()) {
    return errorResponse("SESSION_UNAVAILABLE", "Sign in is not configured.", 503);
  }
  const origin = backendOrigin();
  if (!origin) {
    return errorResponse("SESSION_UNAVAILABLE", "The authentication service is not configured.", 503);
  }

  const contentLength = Number(request.headers.get("content-length") ?? "0");
  if (contentLength > MAX_LOGIN_BODY_BYTES) {
    return errorResponse("REQUEST_TOO_LARGE", "The sign-in request is too large.", 413);
  }

  let body: { email?: unknown; password?: unknown };
  try {
    const raw = await request.text();
    if (new TextEncoder().encode(raw).byteLength > MAX_LOGIN_BODY_BYTES) {
      return errorResponse("REQUEST_TOO_LARGE", "The sign-in request is too large.", 413);
    }
    body = JSON.parse(raw) as typeof body;
  } catch {
    return errorResponse("INVALID_REQUEST", "Enter a valid email and password.", 400);
  }

  const email = typeof body.email === "string" ? body.email.trim() : "";
  if (!email || !email.includes("@") || typeof body.password !== "string" || body.password.length < 1) {
    return errorResponse("INVALID_REQUEST", "Enter a valid email and password.", 400);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), BACKEND_TIMEOUT_MS);
  try {
    const backendResponse = await fetch(origin + "/api/v1/auth/login", {
      method: "POST",
      cache: "no-store",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify({ email, password: body.password }),
      signal: controller.signal,
    });
    const requestId = backendResponse.headers.get("x-request-id");
    const payload = asRecord(await backendResponse.json().catch(() => null));

    if (backendResponse.status === 401) {
      return errorResponse("INVALID_CREDENTIALS", "The email or password is incorrect.", 401, requestId);
    }
    if (backendResponse.status === 429) {
      return errorResponse(
        "RATE_LIMITED",
        "Wait before trying to sign in again.",
        429,
        requestId,
        safeRetryAfter(backendResponse.headers.get("retry-after")),
      );
    }
    if (backendResponse.status === 400 || backendResponse.status === 413 || backendResponse.status === 422) {
      return errorResponse("AUTH_CONTRACT_INVALID", "The authentication request was rejected.", 502, requestId);
    }
    if (!backendResponse.ok || payload?.success !== true) {
      return errorResponse("AUTH_SERVICE_UNAVAILABLE", "The authentication service could not be reached.", 502, requestId);
    }

    const data = asRecord(payload.data);
    const token = pickString(data, "access_token");
    const profile = data ? readProfile(data) : null;
    if (!data || !token || !profile) {
      return errorResponse("AUTH_RESPONSE_INVALID", "The authentication response was incomplete.", 502, requestId);
    }

    // The backend returns expires_in (seconds) in the login response.
    // Fallback to 3600 is a defensive safeguard for older backend versions.
    const expiresIn = typeof data.expires_in === "number" && data.expires_in > 0
      ? data.expires_in
      : 3600;
    await writeSession(token, profile, expiresIn);
    return NextResponse.json({ success: true, data: { user: profile, expires_in: expiresIn } }, {
      headers: requestId ? { "x-request-id": requestId } : undefined,
    });
  } catch {
    return errorResponse("AUTH_SERVICE_UNAVAILABLE", "The authentication service could not be reached.", 502);
  } finally {
    clearTimeout(timeout);
  }
}
