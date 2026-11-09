import type { Metadata } from "next";

import { RouteState } from "@/components/ui/feedback";
import { UUID_PATTERN } from "@/features/documents-list-upload-monitor/api";
import { DocumentDetailView } from "@/features/document-detail-chunk-inspector/document-detail-view";
import { readSession } from "@/lib/auth/session";

export const metadata: Metadata = { title: "Document · DocuSense" };
export const dynamic = "force-dynamic";

export default async function DocumentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const session = await readSession();
  if (!session) return null;
  const { id } = await params;

  if (!UUID_PATTERN.test(id)) {
    return <RouteState kind="not-found" title="Document unavailable" message="This document is unavailable or you do not have access." actionLabel="Back to documents" href="/documents" />;
  }

  return <DocumentDetailView documentId={id} role={session.role} />;
}

