import type { Route } from "next";
import { redirect } from "next/navigation";

import { LoginView, type LoginNotice } from "@/features/auth-login/login-view";
import { safeReturnPath } from "@/lib/auth/return-path";
import { readSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function one(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" ? value : undefined;
}

export default async function LoginPage({ searchParams }: { searchParams: SearchParams }) {
  const query = await searchParams;
  const returnTo = safeReturnPath(one(query.returnTo));
  const session = await readSession();
  if (session) redirect(returnTo as Route);

  let notice: LoginNotice = null;
  if (one(query.reason) === "session-expired") notice = "session-expired";
  else if (one(query.signedOut) === "1") notice = "signed-out";

  return <LoginView returnTo={returnTo} notice={notice} />;
}
