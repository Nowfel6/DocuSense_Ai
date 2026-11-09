import { Badge } from "@/components/ui/feedback";
import { formatDateTime } from "@/lib/formatting/format";

import type { CurrentPreview } from "./types";
import styles from "./human-review-studio.module.css";

const MESSAGE_COPY: Record<string, string> = {
  invoice_total_mismatch: "The invoice total does not match the calculated total.",
  line_total_mismatch: "A line total does not match quantity × unit price plus tax.",
  required_field_missing: "A required value is missing.",
};

export function ValidationPanel({ preview, stale }: { preview?: CurrentPreview; stale: boolean }) {
  if (!preview) {
    return (
      <section className={styles.section} aria-labelledby="validation-heading">
        <h2 id="validation-heading">Validation</h2>
        <p className={styles.emptyText}>Choose Recalculate to preview deterministic checks. No review is saved by previewing.</p>
      </section>
    );
  }
  const report = preview.data.validation;
  const results = [...report.results].sort((a, b) => Number(b.blocks_approval) - Number(a.blocks_approval));
  return (
    <section className={styles.section} aria-labelledby="validation-heading">
      <div className={styles.sectionHeading}>
        <div>
          <h2 id="validation-heading">Validation</h2>
          <p>Calculated locally received at {formatDateTime(preview.receivedAt)}; this preview is not an audit event.</p>
        </div>
        <Badge tone={stale ? "warning" : report.approval_eligible ? "success" : "danger"}>
          {stale ? "Out of date" : report.approval_eligible ? "Eligible" : "Blocked"}
        </Badge>
      </div>
      <dl className={styles.validationSummary}>
        <div><dt>Passed</dt><dd>{report.summary.passed}</dd></div>
        <div><dt>Failed</dt><dd>{report.summary.failed}</dd></div>
        <div><dt>Missing</dt><dd>{report.summary.missing}</dd></div>
        <div><dt>Calculated subtotal</dt><dd>{preview.data.calculated_subtotal ?? "Unavailable"}</dd></div>
        <div><dt>Calculated total</dt><dd>{preview.data.calculated_grand_total ?? "Unavailable"}</dd></div>
      </dl>
      {report.blocking_reasons?.length ? (
        <div className={styles.blockers}><h3>Approval blockers</h3><ul>{report.blocking_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></div>
      ) : null}
      <ul className={styles.ruleList}>
        {results.map((result) => (
          <li key={`${result.rule_id}-${result.scope_key}`}>
            <div><strong>{MESSAGE_COPY[result.message_code] ?? "Validation rule result"}</strong><span>{result.scope_key}</span></div>
            <Badge tone={result.status === "passed" ? "success" : result.blocks_approval ? "danger" : "warning"}>{result.status.replaceAll("_", " ")}</Badge>
          </li>
        ))}
      </ul>
    </section>
  );
}
