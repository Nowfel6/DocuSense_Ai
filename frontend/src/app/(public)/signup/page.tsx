import type { Route } from "next";
import { redirect } from "next/navigation";

import { SignupView, type SignupNotice } from "@/features/auth-signup/signup-view";
import { safeReturnPath } from "@/lib/auth/return-path";
import { readSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function one(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" ? value : undefined;
}

export default async function SignupPage({ searchParams }: { searchParams: SearchParams }) {
  const query = await searchParams;
  const returnTo = safeReturnPath(one(query.returnTo));
  const session = await readSession();
  if (session) redirect(returnTo as Route);

  const notice: SignupNotice = one(query.reason) === "session-expired" ? "session-expired" : null;

  return <SignupView returnTo={returnTo} notice={notice} />;
}
