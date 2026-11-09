export interface ProxyRule {
  method: string;
  path: RegExp;
  largeBody?: boolean;
  maxBodyBytes?: number;
  timeoutMs?: number;
}

export const DEFAULT_JSON_BODY_BYTES = 2 * 1024 * 1024;
export const REVIEW_JSON_BODY_BYTES = 20 * 1024 * 1024;
export const UPLOAD_BODY_BYTES = 55 * 1024 * 1024;

export const PROXY_RULES: ReadonlyArray<ProxyRule> = [
  { method: "POST", path: /^\/api\/v1\/auth\/signup$/ },
  { method: "POST", path: /^\/api\/v1\/documents\/upload$/, largeBody: true, timeoutMs: 120_000 },
  { method: "GET", path: /^\/api\/v1\/documents\/[^/]+\/status$/ },
  { method: "GET", path: /^\/api\/v1\/documents$/ },
  { method: "GET", path: /^\/api\/v1\/documents\/[^/]+\/chunks$/ },
  { method: "GET", path: /^\/api\/v1\/documents\/[^/]+\/extraction-evidence$/ },
  { method: "POST", path: /^\/api\/v1\/documents\/search$/ },
  { method: "GET", path: /^\/api\/v1\/documents\/export$/ },
  { method: "POST", path: /^\/api\/v1\/exports$/ },
  { method: "GET", path: /^\/api\/v1\/exports\/[^/]+\/download$/ },
  { method: "GET", path: /^\/api\/v1\/exports\/[^/]+$/ },
  { method: "GET", path: /^\/api\/v1\/analytics\/dashboard$/ },
  { method: "GET", path: /^\/api\/v1\/activity-events$/ },
  { method: "POST", path: /^\/api\/v1\/documents\/[^/]+\/review-validations$/, maxBodyBytes: REVIEW_JSON_BODY_BYTES },
  { method: "PUT", path: /^\/api\/v1\/documents\/[^/]+\/review$/, maxBodyBytes: REVIEW_JSON_BODY_BYTES },
  { method: "GET", path: /^\/api\/v1\/documents\/[^/]+\/audit-logs$/ },
  { method: "GET", path: /^\/api\/v1\/documents\/[^/]+$/ },
];

export function proxyRuleFor(method: string, path: string): ProxyRule | null {
  return PROXY_RULES.find((rule) => rule.method === method.toUpperCase() && rule.path.test(path)) ?? null;
}

export function maxBodyBytesFor(rule: ProxyRule): number {
  return rule.maxBodyBytes ?? (rule.largeBody ? UPLOAD_BODY_BYTES : DEFAULT_JSON_BODY_BYTES);
}

export function safeApiPath(segments: string[]): string | null {
  if (segments.length < 3 || segments[0] !== "api" || segments[1] !== "v1") return null;
  if (
    segments.some((segment) =>
      !segment || segment === "." || segment === ".." || segment.includes("\\") || segment.includes("/"),
    )
  ) return null;
  return `/${segments.map(encodeURIComponent).join("/")}`;
}

const EXPORT_DOWNLOAD = /^\/api\/v1\/exports\/[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\/download$/i;

export function safeExportRedirectLocation(
  path: string,
  status: number,
  location: string | null,
  configuredOrigins: string | undefined,
): string | null {
  if (!EXPORT_DOWNLOAD.test(path) || status !== 302 || !location || location.length > 2048 || /[\u0000-\u001f\u007f]/.test(location)) return null;
  const origins = new Set((configuredOrigins ?? "").split(",").map((value) => value.trim()).filter(Boolean));
  try {
    const parsed = new URL(location);
    if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.hash || !origins.has(parsed.origin)) return null;
    return parsed.toString();
  } catch {
    return null;
  }
}
