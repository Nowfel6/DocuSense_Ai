import { normalizeWorkbenchQuery } from "@/features/document-detail-chunk-inspector/workbench-query";
import { normalizeSearchUrl } from "@/features/document-search-export/search-query";

const CONTROL_OR_BACKSLASH = /[\\\u0000-\u001f\u007f]/;
const AVAILABLE_AUTHENTICATED_PATHS = new Set(["/dashboard", "/documents", "/documents/upload", "/documents/search"]);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const DOCUMENT_QUERY_VALUES: Record<string, ReadonlySet<string>> = {
  status: new Set(["queued", "partitioning", "chunking", "vectorizing", "extracting", "pending_review", "approved", "rejected", "failed"]),
  doc_type: new Set(["commercial_invoice", "purchase_order", "packing_list"]),
  sort_by: new Set(["created_at", "updated_at", "file_name"]),
  order: new Set(["asc", "desc"]),
  page_size: new Set(["20", "50", "100"]),
};

function sanitizedDocumentSearch(searchParams: URLSearchParams): string {
  const safe = new URLSearchParams();
  const allowed = new Set(["page", "page_size", "status", "doc_type", "from_date", "to_date", "sort_by", "order"]);
  for (const key of allowed) {
    const values = searchParams.getAll(key);
    if (values.length !== 1) continue;
    const value = values[0];
    if (key === "page" && /^[1-9]\d*$/.test(value)) safe.set(key, value);
    else if ((key === "from_date" || key === "to_date") && DATE.test(value)) safe.set(key, value);
    else if (DOCUMENT_QUERY_VALUES[key]?.has(value)) safe.set(key, value);
  }
  return safe.toString();
}

function sanitizedUploadSearch(searchParams: URLSearchParams): string {
  const values = searchParams.getAll("document");
  return values.length === 1 && UUID.test(values[0]) ? `document=${encodeURIComponent(values[0])}` : "";
}

export function safeReturnPath(candidate: string | null | undefined, fallback = "/dashboard"): string {
  if (!candidate || !candidate.startsWith("/") || candidate.startsWith("//")) return fallback;
  if (CONTROL_OR_BACKSLASH.test(candidate)) return fallback;

  try {
    const parsed = new URL(candidate, "https://docusense.invalid");
    if (parsed.origin !== "https://docusense.invalid") return fallback;
    if (parsed.pathname === "/login" || parsed.pathname.startsWith("/api/")) return fallback;
    const documentRoute = parsed.pathname.match(/^\/documents\/([0-9a-f-]{36})(\/(?:chunks|review))?$/i);
    if (documentRoute && UUID.test(documentRoute[1])) {
      if (documentRoute[2] === "/chunks") {
        const canonical = normalizeWorkbenchQuery(parsed.searchParams).canonical;
        return `${parsed.pathname}${canonical ? `?${canonical}` : ""}`;
      }
      if (documentRoute[2] === "/review") return parsed.search || parsed.hash ? fallback : parsed.pathname;
      return parsed.pathname;
    }
    if (!AVAILABLE_AUTHENTICATED_PATHS.has(parsed.pathname)) return fallback;
    if (parsed.pathname === "/dashboard") return `${parsed.pathname}${parsed.search}${parsed.hash}`;
    if (parsed.pathname === "/documents") {
      const search = sanitizedDocumentSearch(parsed.searchParams);
      return `${parsed.pathname}${search ? `?${search}` : ""}`;
    }
    if (parsed.pathname === "/documents/upload") {
      const search = sanitizedUploadSearch(parsed.searchParams);
      return `${parsed.pathname}${search ? `?${search}` : ""}`;
    }
    if (parsed.pathname === "/documents/search") {
      const search = normalizeSearchUrl(parsed.searchParams);
      return `${parsed.pathname}${search ? `?${search}` : ""}`;
    }
    return parsed.pathname;
  } catch {
    return fallback;
  }
}
