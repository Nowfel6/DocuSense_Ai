export function isSameOriginRequest(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;

  const forwardedHost = request.headers.get("x-forwarded-host")?.split(",")[0]?.trim();
  const forwardedProto = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
  const requestUrl = new URL(request.url);
  const expectedOrigin = forwardedHost && forwardedProto
    ? `${forwardedProto}://${forwardedHost}`
    : requestUrl.origin;

  try {
    return new URL(origin).origin === expectedOrigin;
  } catch {
    return false;
  }
}
