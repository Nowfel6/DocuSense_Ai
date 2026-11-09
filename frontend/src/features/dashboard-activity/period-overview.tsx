import { formatDuration, formatInteger, formatRate, formatUtc } from "./format";
import type { DashboardPeriod, PeriodDashboardMetrics } from "./types";

function Facts({ items }: { items: { label: string; value: string; note?: string }[] }) {
  return <dl className="dba-facts">{items.map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd>{item.note ? <span>{item.note}</span> : null}</div>)}</dl>;
}

export function PeriodOverview({ metrics, period }: { metrics: PeriodDashboardMetrics; period: DashboardPeriod }) {
  const headlines = [
    ["Documents uploaded", formatInteger(metrics.documents_uploaded)], ["Processing completed", formatInteger(metrics.processing_completed)],
    ["Processing failed", formatInteger(metrics.processing_failed)], ["Approval events", formatInteger(metrics.approval_events)],
    ["Rejection events", formatInteger(metrics.rejection_events)], ["Exports completed", formatInteger(metrics.exports_completed)],
    ["Exports failed", formatInteger(metrics.exports_failed)], ["Average processing time", formatDuration(metrics.average_successful_processing_ms)],
  ].map(([label, value]) => ({ label, value }));
  return (
    <section aria-labelledby="dba-period-title">
      <div className="dba-section-heading"><div><h2 id="dba-period-title">Period performance</h2><p>{formatUtc(period.from)} to {formatUtc(period.to)} (exclusive), grouped by {period.bucket}.</p></div></div>
      <Facts items={headlines} />
      <div className="dba-quality-grid">
        <article className="dba-quality-panel"><h3>Processing quality</h3><Facts items={[
          { label: "Median processing time", value: formatDuration(metrics.median_successful_processing_ms) },
          { label: "Successful samples", value: formatInteger(metrics.successful_processing_sample_count) },
          { label: "Duration integrity exclusions", value: formatInteger(metrics.processing_duration_integrity_exclusion_count) },
          { label: "Initial deterministic validation pass rate", value: formatRate(metrics.initial_validation_pass_rate), note: `${formatInteger(metrics.initial_validation_passed_run_count)} of ${formatInteger(metrics.initial_validation_eligible_run_count)} eligible runs` },
          { label: "Incomplete rule sets", value: formatInteger(metrics.initial_validation_incomplete_rule_set_count) },
          { label: "Unknown catalogs", value: formatInteger(metrics.initial_validation_unknown_catalog_count) },
          { label: "Failed extraction runs", value: formatInteger(metrics.failed_extraction_run_count) },
        ]} /></article>
        <article className="dba-quality-panel"><h3>Review quality</h3><Facts items={[
          { label: "Reopen events", value: formatInteger(metrics.reopen_events) },
          { label: "Review decisions", value: formatInteger(metrics.review_decision_count) },
          { label: "Reviewed documents", value: formatInteger(metrics.reviewed_document_count) },
          { label: "Approved cycles", value: formatInteger(metrics.approved_cycle_count) },
          { label: "Corrected approvals", value: formatInteger(metrics.corrected_approval_count) },
          { label: "Review correction rate", value: formatRate(metrics.review_correction_rate), note: `${formatInteger(metrics.corrected_approval_count)} of ${formatInteger(metrics.approved_cycle_count)} approved cycles` },
          { label: "Average time to first decision", value: formatDuration(metrics.average_time_to_first_decision_ms), note: `${formatInteger(metrics.first_decision_sample_count)} samples` },
          { label: "Review timing exclusions", value: formatInteger(metrics.review_timing_integrity_exclusion_count) },
        ]} /></article>
      </div>
    </section>
  );
}

