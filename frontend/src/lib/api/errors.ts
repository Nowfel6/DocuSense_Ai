export interface ApiErrorOptions {
  code?: string;
  details?: unknown;
  requestId?: string;
  retryAfterSeconds?: number;
  status?: number;
  cause?: unknown;
}

export class ApiError extends Error {
  readonly code: string;
  readonly details?: unknown;
  readonly requestId?: string;
  readonly retryAfterSeconds?: number;
  readonly status?: number;

  constructor(message: string, options: ApiErrorOptions = {}) {
    super(message, { cause: options.cause });
    this.name = "ApiError";
    this.code = options.code ?? "REQUEST_FAILED";
    this.details = options.details;
    this.requestId = options.requestId;
    this.retryAfterSeconds = options.retryAfterSeconds;
    this.status = options.status;
  }
}

export function parseRetryAfter(value: string | null): number | undefined {
  if (!value || !/^\d+$/.test(value.trim())) return undefined;
  const seconds = Number(value);
  if (!Number.isSafeInteger(seconds)) return undefined;
  return Math.min(30, Math.max(1, seconds));
}

export function normalizeApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (error instanceof DOMException && error.name === "AbortError") {
    return new ApiError("The request was canceled.", { code: "REQUEST_ABORTED", cause: error });
  }
  if (error instanceof Error) {
    return new ApiError("The service could not be reached. Try again.", {
      code: "NETWORK_ERROR",
      cause: error,
    });
  }
  return new ApiError("An unexpected request error occurred.", { cause: error });
}
