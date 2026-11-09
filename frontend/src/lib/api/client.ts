import { ApiError, normalizeApiError, parseRetryAfter } from "./errors";

export interface SuccessEnvelope<T> {
  success: true;
  data: T;
  message?: string;
  meta?: { request_id?: string; [key: string]: unknown };
  [key: string]: unknown;
}

export interface ErrorEnvelope {
  success: false;
  error?: { code?: string; message?: string; details?: unknown };
  request_id?: string;
  meta?: { request_id?: string; [key: string]: unknown };
}

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  body?: BodyInit | Record<string, unknown> | null;
  timeoutMs?: number;
  responseType?: "json" | "blob";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value)
    && typeof value === "object"
    && !Array.isArray(value)
    && Object.getPrototypeOf(value) === Object.prototype;
}

export function apiErrorFromPayload(
  payload: unknown,
  status: number,
  headers?: Pick<Headers, "get">,
): ApiError {
  const failure = isRecord(payload) && payload.success === false ? payload as unknown as ErrorEnvelope : null;
  return new ApiError(failure?.error?.message ?? "The request could not be completed.", {
    code: failure?.error?.code ?? `HTTP_${status}`,
    details: failure?.error?.details,
    requestId: failure?.meta?.request_id ?? failure?.request_id ?? headers?.get("x-request-id") ?? undefined,
    retryAfterSeconds: parseRetryAfter(headers?.get("retry-after") ?? null),
    status,
  });
}

async function executeRequest<T>(
  path: `/api/v1/${string}` | "/api/v1/documents",
  options: ApiRequestOptions,
  completeEnvelope: boolean,
): Promise<{ value: T; status: number; headers: Headers }> {
  const { timeoutMs = 30_000, responseType = "json", headers, body, signal, ...init } = options;
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  const combinedSignal = signal ? AbortSignal.any([signal, controller.signal]) : controller.signal;
  const requestHeaders = new Headers(headers);
  let requestBody = body as BodyInit | null | undefined;

  if (isRecord(body)) {
    requestHeaders.set("content-type", "application/json");
    requestBody = JSON.stringify(body);
  }
  requestHeaders.set("accept", responseType === "blob" ? "application/octet-stream" : "application/json");

  try {
    const response = await fetch(`/api/backend${path}`, {
      ...init,
      body: requestBody,
      cache: "no-store",
      credentials: "same-origin",
      headers: requestHeaders,
      signal: combinedSignal,
    });

    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("docusense:session-expired", {
        detail: { returnTo: window.location.pathname + window.location.search },
      }));
    }

    if (responseType === "blob" && response.ok) return { value: await response.blob() as T, status: response.status, headers: response.headers };

    const payload = await response.json().catch(() => null) as SuccessEnvelope<unknown> | ErrorEnvelope | null;
    if (response.ok && payload?.success === true) {
      return { value: (completeEnvelope ? payload : payload.data) as T, status: response.status, headers: response.headers };
    }
    throw apiErrorFromPayload(payload, response.status, response.headers);
  } catch (error) {
    throw normalizeApiError(error);
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export async function apiRequest<T>(path: `/api/v1/${string}` | "/api/v1/documents", options: ApiRequestOptions = {}): Promise<T> {
  return (await executeRequest<T>(path, options, false)).value;
}

export async function apiEnvelopeRequest<TEnvelope>(
  path: `/api/v1/${string}` | "/api/v1/documents",
  options: ApiRequestOptions = {},
): Promise<TEnvelope> {
  return (await executeRequest<TEnvelope>(path, options, true)).value;
}

export async function apiResponseRequest<TEnvelope>(
  path: `/api/v1/${string}` | "/api/v1/documents",
  options: ApiRequestOptions = {},
): Promise<{ data: TEnvelope; status: number; headers: Headers }> {
  const response = await executeRequest<TEnvelope>(path, options, true);
  return { data: response.value, status: response.status, headers: response.headers };
}
