import type { Metadata } from "next";

import { DocumentSearchExportHub } from "@/features/document-search-export/document-search-export-hub";
import { parseSearchUrl } from "@/features/document-search-export/search-query";
import { readSession } from "@/lib/auth/session";

export const metadata: Metadata = { title: "Search & export · DocuSense" };
export const dynamic = "force-dynamic";

export default async function DocumentSearchPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const session = await readSession();
  if (!session) return null;
  const incoming = await searchParams;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(incoming)) {
    if (Array.isArray(value)) value.forEach((entry) => params.append(key, entry));
    else if (value !== undefined) params.set(key, value);
  }
  return <DocumentSearchExportHub role={session.role} initialState={parseSearchUrl(params)} />;
}
