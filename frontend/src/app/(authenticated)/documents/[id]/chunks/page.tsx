import type { Metadata } from "next";

import { RouteState } from "@/components/ui/feedback";
import { ChunkEvidenceWorkbench } from "@/features/document-detail-chunk-inspector/workbench-view";
import { UUID_PATTERN } from "@/features/documents-list-upload-monitor/api";
import { readSession } from "@/lib/auth/session";

export const metadata: Metadata = { title: "Chunk and evidence workbench · DocuSense" };
export const dynamic = "force-dynamic";

export default async function ChunkEvidencePage({ params }: { params: Promise<{ id: string }> }) {
  const session = await readSession();
  if (!session) return null;
  const { id } = await params;

  if (!UUID_PATTERN.test(id)) {
    return <RouteState kind="not-found" title="Document unavailable" message="This document is unavailable or you do not have access." actionLabel="Back to documents" href="/documents" />;
  }
  if (session.role === "viewer") {
    return <RouteState kind="forbidden" title="Workbench unavailable" message="Technical chunks and extraction evidence are restricted to administrators and operators." actionLabel="Back to document" href={`/documents/${id}`} />;
  }

  return <ChunkEvidenceWorkbench documentId={id} />;
}

