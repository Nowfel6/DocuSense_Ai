import type { Metadata } from "next";

import { RouteState } from "@/components/ui/feedback";
import { SettingsApiPlaceholderView } from "@/features/settings-api-placeholder/settings-api-placeholder-view";
import { readSession } from "@/lib/auth/session";

export const metadata: Metadata = { title: "API & Integrations · DocuSense" };
export const dynamic = "force-dynamic";

export default async function SettingsApiPage() {
  const session = await readSession();

  if (!session) return null;

  if (session.role !== "admin") {
    return (
      <RouteState
        kind="forbidden"
        title="API & integrations unavailable"
        message="This area is restricted to administrators."
        actionLabel="Back to dashboard"
        href="/dashboard"
      />
    );
  }

  return <SettingsApiPlaceholderView />;
}

