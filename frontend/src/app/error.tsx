"use client";

import { useEffect } from "react";

import { RouteState } from "@/components/ui/feedback";

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Report only the opaque digest; never expose raw errors to the UI.
    if (error.digest) console.error("Route error digest", error.digest);
  }, [error.digest]);

  return (
    <main className="ds-public-content" id="main-content">
      <RouteState
        kind="error"
        title="Something went wrong"
        message="The page could not be loaded safely. Try again."
        requestId={error.digest}
        actionLabel="Try again"
        onAction={reset}
      />
    </main>
  );
}
