"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";

import { safeReturnPath } from "@/lib/auth/return-path";

export function SessionRequiredRedirect() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const search = searchParams.toString();
  const returnTo = safeReturnPath(`${pathname}${search ? `?${search}` : ""}`);
  const loginHref = `/login?returnTo=${encodeURIComponent(returnTo)}` as Route;

  useEffect(() => { router.replace(loginHref); }, [loginHref, router]);

  return (
    <main className="ds-route-main" id="main-content">
      <section className="ds-route-state" aria-labelledby="session-required-title">
        <h1 id="session-required-title">Sign in required</h1>
        <p>Redirecting you to sign in.</p>
        <Link className="ds-button" data-variant="primary" href={loginHref}>Continue to sign in</Link>
      </section>
    </main>
  );
}
