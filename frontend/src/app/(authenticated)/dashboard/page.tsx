import type { Metadata } from "next";

import { parseDashboardUrl } from "@/features/dashboard-activity/api";
import { DashboardActivityView } from "@/features/dashboard-activity/dashboard-activity-view";
import { readSession } from "@/lib/auth/session";

export const metadata: Metadata = { title: "Dashboard · DocuSense" };
export const dynamic = "force-dynamic";

export default async function DashboardPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const session = await readSession();
  if (!session) return null;
  const incoming = await searchParams;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(incoming)) {
    if (Array.isArray(value)) value.forEach((entry) => params.append(key, entry));
    else if (value !== undefined) params.set(key, value);
  }
  return <DashboardActivityView role={session.role} initialState={parseDashboardUrl(params)} />;
}
