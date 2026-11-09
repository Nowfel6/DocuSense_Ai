"use client";

import type { Route } from "next";
import Link from "next/link";

import { Alert } from "@/components/ui/feedback";

import { LoginForm } from "./login-form";

export type LoginNotice = "session-expired" | "signed-out" | null;

function Notice({ notice }: { notice: LoginNotice }) {
  if (notice === "session-expired") {
    return <Alert tone="warning" title="Your session ended" message="Sign in again to continue." />;
  }
  if (notice === "signed-out") {
    return <Alert tone="success" title="You’re signed out" message="Your session was cleared on this device." />;
  }
  return null;
}

export function LoginView({ returnTo, notice }: { returnTo: string; notice: LoginNotice }) {
  return (
    <section className="ds-login-card" aria-labelledby="login-title">
      <div className="ds-login-heading">
        <h1 id="login-title">Sign in to DocuSense</h1>
        <p>Use your organization account to continue.</p>
      </div>
      <Notice notice={notice} />
      <LoginForm returnTo={returnTo} />
      <p className="ds-login-footer">
        New to DocuSense? <Link href={`/signup?returnTo=${encodeURIComponent(returnTo)}` as Route}>Create a workspace</Link>.
      </p>
      <p className="ds-login-security-note">Your session is protected on this device.</p>
    </section>
  );
}
