import type { Metadata } from "next";

import { DocumentsView } from "@/features/documents-list-upload-monitor/documents-view";
import { readSession } from "@/lib/auth/session";

export const metadata: Metadata = { title: "Documents · DocuSense" };
export const dynamic = "force-dynamic";

export default async function DocumentsPage() {
  const session = await readSession();
  if (!session) return null;
  return <DocumentsView role={session.role} />;
}
