import type { ReactNode } from "react";

import { Wordmark } from "./wordmark";
import { SkipLink } from "./skip-link";

export function PublicShell({ children }: { children: ReactNode }) {
  return (
    <div className="ds-public-shell">
      <SkipLink />
      <header className="ds-public-header"><Wordmark href="/" /></header>
      <main className="ds-public-content" id="main-content" tabIndex={-1}>{children}</main>
    </div>
  );
}
