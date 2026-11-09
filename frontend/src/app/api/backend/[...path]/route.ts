import { NextResponse } from "next/server";

import { maxBodyBytesFor, proxyRuleFor, safeApiPath, safeExportRedirectLocation } from "@/lib/api/proxy-policy";
import { isSameOriginRequest } from "@/lib/auth/request-security";
import { clearSession, readAccessToken } from "@/lib/auth/session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const FORWARDED_REQUEST_HEADERS = ["accept", "content-type", "idempotency-key", "if-match"];
const FORWARDED_RESPONSE_HEADERS = ["content-type", "content-disposition", "cache-control", "pragma", "x-content-type-options", "x-content-sha256", "x-export-id", "x-request-id", "retry-after"];

function errorResponse(code: string, message: string, status: number) {
  return NextResponse.json({ success: false, error: { code, message } }, { status, headers: { "cache-control": "private, no-store" } });
}

function configuredBackendOrigin(): string | null {
  const configured = process.env.BACKEND_API_ORIGIN;
  if (!configured) return null;
  try {
    const parsed = new URL(configured);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const path = safeApiPath((await context.params).path);
  if (!path) return errorResponse("PROXY_PATH_DENIED", "This API path is not available.", 404);
  const rule = proxyRuleFor(request.method, path);
  if (!rule) return errorResponse("PROXY_PATH_DENIED", "This API operation is not available.", 404);
  if (MUTATING_METHODS.has(request.method) && !isSameOriginRequest(request)) {
    return errorResponse("INVALID_ORIGIN", "The request origin could not be verified.", 403);
  }

  const token = await readAccessToken();
  if (!token) return errorResponse("SESSION_REQUIRED", "Sign in is required.", 401);
  const backendOrigin = configuredBackendOrigin();
  if (!backendOrigin) return errorResponse("BACKEND_UNAVAILABLE", "The backend service is not configured.", 503);

  const maxBodyBytes = maxBodyBytesFor(rule);
  const contentLength = Number(request.headers.get("content-length") ?? "0");
  if (!Number.isFinite(contentLength) || contentLength > maxBodyBytes) {
    return errorResponse("REQUEST_TOO_LARGE", "The request is too large.", 413);
  }

  let body: ArrayBuffer | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    body = await request.arrayBuffer();
    if (body.byteLength > maxBodyBytes) {
      return errorResponse("REQUEST_TOO_LARGE", "The request is too large.", 413);
    }
  }

  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("authorization", `Bearer ${token}`);

  const query = new URL(request.url).search;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), rule.timeoutMs ?? 30_000);

  try {
    const response = await fetch(`${backendOrigin}${path}${query}`, {
      method: request.method,
      body,
      cache: "no-store",
      headers,
      redirect: "manual",
      signal: controller.signal,
    });

    if (response.status === 401) await clearSession();
    const responseHeaders = new Headers({ "cache-control": "no-store, private" });
    for (const name of FORWARDED_RESPONSE_HEADERS) {
      const value = response.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    if (response.status === 302) {
      const location = safeExportRedirectLocation(path, response.status, response.headers.get("location"), process.env.EXPORT_DOWNLOAD_ALLOWED_ORIGINS);
      if (!location) return errorResponse("INVALID_EXPORT_REDIRECT", "The export download location was rejected.", 502);
      responseHeaders.set("location", location);
    }
    return new Response(response.body, { status: response.status, headers: responseHeaders });
  } catch {
    return errorResponse("BACKEND_UNAVAILABLE", "The backend service could not be reached.", 502);
  } finally {
    clearTimeout(timeout);
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
