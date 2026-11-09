import type { Route } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { SkipLink } from "@/components/shell/skip-link";
import { Wordmark } from "@/components/shell/wordmark";

import styles from "./public-landing.module.css";

export function LandingShell({ children }: { children: ReactNode }) {
  return (
    <div className={styles.shell}>
      <SkipLink />
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <Wordmark href="/" />
          <div className={styles.headerActions}>
            <Link className={`ds-button ${styles.headerAction}`} data-variant="secondary" href={"/signup" as Route}>
              Sign up
            </Link>
            <Link className={`ds-button ${styles.headerAction}`} data-variant="primary" href="/login">
              Sign in
            </Link>
          </div>
        </div>
      </header>
      <main className={styles.main} id="main-content" tabIndex={-1}>
        {children}
      </main>
      <footer className={styles.footer}>
        <p>DocuSense · Traceable document processing and human review.</p>
      </footer>
    </div>
  );
}
