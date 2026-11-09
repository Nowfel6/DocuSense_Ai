import { NextResponse } from "next/server";

import { isSameOriginRequest } from "@/lib/auth/request-security";
import { isSessionConfigurationReady, writeSession } from "@/lib/auth/session";
import type { SessionProfile } from "@/lib/auth/session-types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_SIGNUP_BODY_BYTES = 8 * 1024;
const BACKEND_TIMEOUT_MS = 15_000;

type SignupErrorCode =
  | "INVALID_REQUEST"
  | "EMAIL_TAKEN"
  | "INVALID_ORIGIN"
  | "REQUEST_TOO_LARGE"
  | "RATE_LIMITED"
  | "AUTH_CONTRACT_INVALID"
  | "AUTH_SERVICE_UNAVAILABLE"
  | "AUTH_RESPONSE_INVALID"
  | "SESSION_UNAVAILABLE"
  | "VALIDATION_ERROR";

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

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function isUserRole(value: unknown): value is SessionProfile["role"] {
  return value === "admin" || value === "operator" || value === "viewer";
}

function pickString(record: Record<string, unknown> | null, ...keys: string[]): string | null {
  for (const key of keys) {
    if (typeof record?.[key] === "string" && (record[key] as string)) return record[key] as string;
  }
  return null;
}

function readProfile(data: Record<string, unknown>): SessionProfile | null {
  const user = asRecord(data.user);
  const role = user?.role;
  if (!user || !isUserRole(role)) return null;
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
  code: SignupErrorCode,
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

const EMAIL = /^[^\s@]+@[^\s@]+$/;
const ISO_COUNTRY = /^[A-Z]{2}$/;
const SIGNUP_BUSINESS_TYPES = new Set(["importer", "trading", "logistics"]);

function validateClientSide(
  body: Record<string, unknown>,
): { ok: true; value: NormalizedSignup } | { ok: false; message: string } {
  const fullName = typeof body.full_name === "string" ? body.full_name.trim() : "";
  const organizationName = typeof body.organization_name === "string" ? body.organization_name.trim() : "";
  const businessType = typeof body.business_type === "string" ? body.business_type.trim().toLowerCase() : "";
  const country = typeof body.country === "string" ? body.country.trim().toUpperCase() : "";
  const email = typeof body.email === "string" ? body.email.trim() : "";
  const password = typeof body.password === "string" ? body.password : "";
  const agreeToTerms = body.agree_to_terms === true;

  if (!fullName || fullName.length > 100) return { ok: false, message: "Enter your full name." };
  if (!organizationName || organizationName.length > 255) return { ok: false, message: "Enter your organization name." };
  if (!SIGNUP_BUSINESS_TYPES.has(businessType)) return { ok: false, message: "Pick a business type." };
  if (!ISO_COUNTRY.test(country)) return { ok: false, message: "Pick a country." };
  if (!EMAIL.test(email) || email.length > 255) return { ok: false, message: "Enter a valid work email." };
  if (password.length < 8 || password.length > 128) {
    return { ok: false, message: "Password must be 8–128 characters." };
  }
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
    return { ok: false, message: "Password must include at least one letter and one number." };
  }
  if (!agreeToTerms) return { ok: false, message: "Accept the terms to continue." };

  return {
    ok: true,
    value: {
      full_name: fullName,
      organization_name: organizationName,
      business_type: businessType,
      country,
      email,
      password,
      agree_to_terms: true,
    },
  };
}

interface NormalizedSignup {
  full_name: string;
  organization_name: string;
  business_type: string;
  country: string;
  email: string;
  password: string;
  agree_to_terms: true;
}

export async function POST(request: Request) {
  if (!isSameOriginRequest(request)) {
    return errorResponse("INVALID_ORIGIN", "The request origin could not be verified.", 403);
  }
  if (!isSessionConfigurationReady()) {
    return errorResponse("SESSION_UNAVAILABLE", "Sign up is not configured.", 503);
  }
  const origin = backendOrigin();
  if (!origin) {
    return errorResponse("SESSION_UNAVAILABLE", "The authentication service is not configured.", 503);
  }

  const contentLength = Number(request.headers.get("content-length") ?? "0");
  if (contentLength > MAX_SIGNUP_BODY_BYTES) {
    return errorResponse("REQUEST_TOO_LARGE", "The sign-up request is too large.", 413);
  }

  let body: Record<string, unknown>;
  try {
    const raw = await request.text();
    if (new TextEncoder().encode(raw).byteLength > MAX_SIGNUP_BODY_BYTES) {
      return errorResponse("REQUEST_TOO_LARGE", "The sign-up request is too large.", 413);
    }
    const parsed = JSON.parse(raw);
    body = asRecord(parsed) ?? {};
  } catch {
    return errorResponse("INVALID_REQUEST", "Complete every field before submitting.", 400);
  }

  const validation = validateClientSide(body);
  if (!validation.ok) {
    return errorResponse("INVALID_REQUEST", validation.message, 400);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), BACKEND_TIMEOUT_MS);
  try {
    const backendResponse = await fetch(origin + "/api/v1/auth/signup", {
      method: "POST",
      cache: "no-store",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify(validation.value),
      signal: controller.signal,
    });
    const requestId = backendResponse.headers.get("x-request-id");
    const payload = asRecord(await backendResponse.json().catch(() => null));

    if (backendResponse.status === 409) {
      return errorResponse(
        "EMAIL_TAKEN",
        "An account with this email already exists. Try signing in instead.",
        409,
        requestId,
      );
    }
    if (backendResponse.status === 429) {
      return errorResponse(
        "RATE_LIMITED",
        "Wait before trying to sign up again.",
        429,
        requestId,
        safeRetryAfter(backendResponse.headers.get("retry-after")),
      );
    }
    if (backendResponse.status === 400 || backendResponse.status === 413 || backendResponse.status === 422) {
      const detail = asRecord(payload?.detail);
      const detailCode = typeof detail?.code === "string" ? detail.code : undefined;
      return errorResponse(
        detailCode === "VALIDATION_ERROR" ? "VALIDATION_ERROR" : "AUTH_CONTRACT_INVALID",
        "The sign-up request was rejected.",
        400,
        requestId,
      );
    }
    if (!backendResponse.ok || payload?.success !== true) {
      return errorResponse(
        "AUTH_SERVICE_UNAVAILABLE",
        "The authentication service could not be reached.",
        502,
        requestId,
      );
    }

    const data = asRecord(payload.data);
    const token = pickString(data, "access_token");
    const profile = data ? readProfile(data) : null;
    if (!data || !token || !profile) {
      return errorResponse(
        "AUTH_RESPONSE_INVALID",
        "The authentication response was incomplete.",
        502,
        requestId,
      );
    }

    const expiresIn = typeof data.expires_in === "number" && data.expires_in > 0
      ? data.expires_in
      : 3600;
    await writeSession(token, profile, expiresIn);
    return NextResponse.json({ success: true, data: { user: profile, expires_in: expiresIn } }, {
      headers: requestId ? { "x-request-id": requestId } : undefined,
    });
  } catch {
    return errorResponse(
      "AUTH_SERVICE_UNAVAILABLE",
      "The authentication service could not be reached.",
      502,
    );
  } finally {
    clearTimeout(timeout);
  }
}
