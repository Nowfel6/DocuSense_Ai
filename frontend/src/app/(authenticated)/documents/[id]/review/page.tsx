import type { Metadata } from "next";

import { RouteState } from "@/components/ui/feedback";
import { UUID_PATTERN } from "@/features/documents-list-upload-monitor/api";
import { HumanReviewStudio } from "@/features/human-review-studio/review-studio-view";
import { readSession } from "@/lib/auth/session";

export const metadata: Metadata = { title: "Human review · DocuSense" };
export const dynamic = "force-dynamic";

export default async function HumanReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const session = await readSession();
  if (!session) return null;
  const { id } = await params;
  if (!UUID_PATTERN.test(id)) return <RouteState kind="not-found" title="Review unavailable" message="This review is unavailable or you do not have access." actionLabel="Back to documents" href="/documents" />;
  if (session.role === "viewer") return <RouteState kind="forbidden" title="Review unavailable" message="Human review is restricted to administrators and operators." actionLabel="Back to documents" href="/documents" />;
  return <HumanReviewStudio documentId={id} />;
}
