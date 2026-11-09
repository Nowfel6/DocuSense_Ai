"use client";

import Link from "next/link";

import { Alert } from "@/components/ui/feedback";

import { SignupForm } from "./signup-form";

export type SignupNotice = "session-expired" | null;

function Notice({ notice }: { notice: SignupNotice }) {
  if (notice === "session-expired") {
    return <Alert tone="warning" title="Your session ended" message="Sign in again or create a new workspace to continue." />;
  }
  return null;
}

export function SignupView({ returnTo, notice }: { returnTo: string; notice: SignupNotice }) {
  return (
    <section className="ds-signup-card" aria-labelledby="signup-title">
      <div className="ds-signup-heading">
        <h1 id="signup-title">Create your DocuSense workspace</h1>
        <p>Start a fresh tenant — you’ll become the workspace administrator.</p>
      </div>
      <Notice notice={notice} />
      <SignupForm returnTo={returnTo} />
      <p className="ds-signup-footer">
        Already have an account? <Link href={`/login?returnTo=${encodeURIComponent(returnTo)}`}>Sign in</Link>.
      </p>
      <p className="ds-signup-security-note">Your session is protected on this device.</p>
    </section>
  );
}
