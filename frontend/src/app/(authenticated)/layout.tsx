import { Suspense, type ReactNode } from "react";

import { AppShell } from "@/components/shell/app-shell";
import { SessionRequiredRedirect } from "@/components/shell/session-required-redirect";
import { readSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export default async function AuthenticatedLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  const session = await readSession();

  if (!session) {
    return <Suspense fallback={null}><SessionRequiredRedirect /></Suspense>;
  }

  return (
    <AppShell
      profile={session}
      notificationCount={null}
    >
      {children}
    </AppShell>
  );
}
