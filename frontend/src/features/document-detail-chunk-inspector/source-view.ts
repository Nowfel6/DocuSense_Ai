import type { SourceView } from "./types";

const SOURCE_EXPIRY_SAFETY_MS = 30_000;

export function isSafeSourceUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password;
  } catch {
    return false;
  }
}

export function sourceIsExpired(source: SourceView, now = Date.now()): boolean {
  const expiresAt = Date.parse(source.expires_at);
  return !Number.isFinite(expiresAt) || expiresAt <= now + SOURCE_EXPIRY_SAFETY_MS;
}

export function sourceHref(source: SourceView, page?: number): string | null {
  if (!isSafeSourceUrl(source.url) || sourceIsExpired(source)) return null;
  const url = new URL(source.url);
  if (source.mime_type === "application/pdf" && Number.isSafeInteger(page) && (page ?? 0) >= 1) {
    url.hash = `page=${page}`;
  }
  return url.toString();
}

export function millisecondsUntilSourceRefresh(source: SourceView, now = Date.now()): number {
  const expiresAt = Date.parse(source.expires_at);
  if (!Number.isFinite(expiresAt)) return 0;
  return Math.max(0, expiresAt - now - SOURCE_EXPIRY_SAFETY_MS);
}

