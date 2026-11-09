import type { Metadata } from "next";

import { LandingShell } from "@/features/public-landing/landing-shell";
import { PublicLandingView } from "@/features/public-landing/public-landing-view";

export const metadata: Metadata = {
  title: "Traceable document intelligence",
  description:
    "Turn complex documents into evidence-backed decisions with traceable extraction, deterministic validation, and human review.",
};

export default function PublicHomePage() {
  return (
    <LandingShell>
      <PublicLandingView />
    </LandingShell>
  );
}
