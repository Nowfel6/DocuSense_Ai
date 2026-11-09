import { formatInteger, formatUtc } from "./format";
import type { CurrentDashboardMetrics } from "./types";

const cards: [keyof CurrentDashboardMetrics, string][] = [
  ["total_documents", "Total documents"],
  ["active_processing_documents", "Processing now"],
  ["pending_review_documents", "Pending review"],
  ["approved_documents", "Approved"],
  ["failed_documents", "Failed"],
  ["active_export_jobs", "Active exports"],
];

export function CurrentWorkload({ metrics, snapshot }: { metrics: CurrentDashboardMetrics; snapshot: string }) {
  return (
    <section aria-labelledby="dba-current-title">
      <div className="dba-section-heading"><div><h2 id="dba-current-title">Current workload</h2><p>As of {formatUtc(snapshot)}. These counts are not limited by the report period.</p></div></div>
      <dl className="dba-metric-grid">
        {cards.map(([key, label]) => <div className="dba-metric-card" data-risk={key === "failed_documents" || undefined} key={key}><dt>{label}</dt><dd>{formatInteger(metrics[key])}</dd><span>Current</span></div>)}
      </dl>
    </section>
  );
}

