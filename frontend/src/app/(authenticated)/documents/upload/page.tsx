import type { Metadata } from "next";

import { RouteState } from "@/components/ui/feedback";
import { UploadMonitorView } from "@/features/documents-list-upload-monitor/upload-monitor-view";
import { readSession } from "@/lib/auth/session";

export const metadata: Metadata = { title: "Upload document · DocuSense" };
export const dynamic = "force-dynamic";

export default async function UploadDocumentPage() {
  const session = await readSession();
  if (!session) return null;
  if (session.role === "viewer") {
    return <RouteState kind="forbidden" title="Upload unavailable" message="Your role can browse approved documents but cannot upload new documents." actionLabel="Back to documents" href="/documents" />;
  }
  return <UploadMonitorView />;
}
