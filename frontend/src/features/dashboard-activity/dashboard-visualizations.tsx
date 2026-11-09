import { AccessibleDataTable } from "./accessible-data-table";
import { formatBucket, formatDuration, statusLabel } from "./format";
import type { DashboardData } from "./types";

interface BarRow { label: string; values: { label: string; value: number | null; display?: string }[] }

function Bars({ rows }: { rows: BarRow[] }) {
  const maximum = Math.max(1, ...rows.flatMap((row) => row.values.flatMap((item) => item.value === null ? [] : [item.value])));
  return <div className="dba-bar-chart" aria-hidden="true">{rows.map((row) => <div className="dba-bar-row" key={row.label}><span>{row.label}</span><div>{row.values.map((item, index) => <i key={item.label} data-series={index % 4} data-missing={item.value === null || undefined} style={{ width: item.value === null ? undefined : `${Math.max(item.value ? 2 : 0, item.value / maximum * 100)}%` }} title={`${item.label}: ${item.display ?? item.value ?? "No data"}`} />)}</div></div>)}</div>;
}

function BarPanel({ title, description, rows, tableHeaders, tableRows }: { title: string; description: string; rows: BarRow[]; tableHeaders: string[]; tableRows: (string | number)[][] }) {
  return (
    <article className="dba-chart-card">
      <div><h3>{title}</h3><p>{description}</p></div>
      <Bars rows={rows} />
      <ul className="dba-legend" aria-label={`${title} legend`}>{rows[0]?.values.map((item, index) => <li key={item.label}><i data-series={index % 4} />{item.label}</li>)}</ul>
      <AccessibleDataTable caption={`${title} exact values`} headers={tableHeaders} rows={tableRows} />
    </article>
  );
}

function ReviewPanel({ data }: { data: DashboardData }) {
  const decisions: BarRow[] = data.trends.review_decisions.map((point) => ({ label: formatBucket(point.bucket_start), values: [{ label: "Approved", value: point.approved }, { label: "Rejected", value: point.rejected }, { label: "Reopened", value: point.reopened }] }));
  const backlog: BarRow[] = data.trends.review_backlog_end_of_bucket.map((point) => ({ label: formatBucket(point.bucket_start), values: [{ label: "Backlog", value: point.review_backlog_end_of_bucket }] }));
  return <article className="dba-chart-card"><div><h3>Review decisions and backlog</h3><p>Decision events and backlog use aligned buckets with separate scales.</p></div><h4 className="dba-chart-subtitle">Decision events</h4><Bars rows={decisions} /><ul className="dba-legend" aria-label="Review decision legend">{decisions[0].values.map((item, index) => <li key={item.label}><i data-series={index} />{item.label}</li>)}</ul><h4 className="dba-chart-subtitle">End-of-bucket backlog</h4><Bars rows={backlog} /><AccessibleDataTable caption="Review decisions and backlog exact values" headers={["Bucket", "Approved", "Rejected", "Reopened", "Backlog"]} rows={data.trends.review_decisions.map((point, index) => [formatBucket(point.bucket_start), point.approved, point.rejected, point.reopened, data.trends.review_backlog_end_of_bucket[index].review_backlog_end_of_bucket])} /></article>;
}

export function DashboardVisualizations({ data }: { data: DashboardData }) {
  const volumeRows = data.trends.document_volume.map((point) => ({ label: formatBucket(point.bucket_start), values: [{ label: "Uploaded", value: point.uploaded }, { label: "Completed", value: point.processing_completed }, { label: "Failed", value: point.processing_failed }] }));
  const statusRows = data.status_distribution.map((point) => ({ label: statusLabel(point.status), values: [{ label: "Documents", value: point.count }] }));
  const durationRows = data.trends.successful_processing_duration.map((point) => ({ label: formatBucket(point.bucket_start), values: [{ label: "Average", value: point.average_ms, display: formatDuration(point.average_ms) }, { label: "Median", value: point.median_ms, display: formatDuration(point.median_ms) }] }));
  const exportRows = data.trends.export_outcomes.map((point) => ({ label: formatBucket(point.bucket_start), values: [{ label: "Completed", value: point.completed }, { label: "Failed", value: point.failed }] }));
  return (
    <section aria-labelledby="dba-trends-title">
      <div className="dba-section-heading"><div><h2 id="dba-trends-title">Trends and distribution</h2><p>Visual summaries are paired with exact-value tables.</p></div></div>
      <div className="dba-chart-grid">
        <BarPanel title="Document volume" description="Uploads and processing outcomes by bucket." rows={volumeRows} tableHeaders={["Bucket", "Uploaded", "Completed", "Failed"]} tableRows={data.trends.document_volume.map((p) => [formatBucket(p.bucket_start), p.uploaded, p.processing_completed, p.processing_failed])} />
        <BarPanel title="Status distribution" description="Current documents across all workflow states." rows={statusRows} tableHeaders={["Status", "Documents"]} tableRows={data.status_distribution.map((p) => [statusLabel(p.status), p.count])} />
        <ReviewPanel data={data} />
        <BarPanel title="Successful processing duration" description="Average and median successful processing time." rows={durationRows} tableHeaders={["Bucket", "Average ms", "Median ms", "Samples", "Integrity exclusions"]} tableRows={data.trends.successful_processing_duration.map((p) => [formatBucket(p.bucket_start), p.average_ms ?? "No data", p.median_ms ?? "No data", p.sample_count, p.integrity_exclusion_count])} />
        <BarPanel title="Export outcomes" description="Completed and failed exports by bucket." rows={exportRows} tableHeaders={["Bucket", "Completed", "Failed"]} tableRows={data.trends.export_outcomes.map((p) => [formatBucket(p.bucket_start), p.completed, p.failed])} />
      </div>
    </section>
  );
}
