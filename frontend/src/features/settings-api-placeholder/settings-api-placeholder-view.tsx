import Link from "next/link";

import { Badge } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";

import styles from "./settings-api-placeholder.module.css";

export function SettingsApiPlaceholderView() {
  return (
    <div className={styles.page}>
      <PageHeader
        title="API & Integrations"
        description="Programmatic access and event delivery for external systems."
      />

      <section className={styles.panel} aria-labelledby="developer-access-heading">
        <div className={styles.statusRow}>
          <Badge tone="warning">Not enabled in this release</Badge>
        </div>

        <div className={styles.copy}>
          <h2 id="developer-access-heading">Developer access is coming later</h2>
          <p>
            API keys and webhook integrations are planned for a future release. They are not
            available or configured in this workspace today.
          </p>
          <p>
            You can continue using DocuSense through the authenticated application. No setup is
            required for this page.
          </p>
        </div>

        <ul className={styles.plannedAreas}>
          <li><strong>Programmatic API keys</strong> for approved external access.</li>
          <li><strong>Signed webhook notifications</strong> for future event delivery.</li>
        </ul>

        <div className={styles.actions}>
          <Link className="ds-button" data-variant="secondary" href="/dashboard">
            Return to dashboard
          </Link>
        </div>
      </section>
    </div>
  );
}

