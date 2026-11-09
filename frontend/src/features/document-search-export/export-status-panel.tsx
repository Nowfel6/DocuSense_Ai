import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/feedback";
import { formatDateTime } from "@/lib/formatting/format";

import { publicExportError, statusTone } from "./api";
import { exportDownloadPath } from "./format";
import type { ExportResource } from "./types";

export function ExportStatusPanel({ resource, stale, error, onRefresh, onDismiss, onNewExport, idPrefix = "rail" }: {
  resource: ExportResource;
  stale: boolean;
  error: string | null;
  onRefresh: () => void;
  onDismiss: () => void;
  onNewExport: () => void;
  idPrefix?: string;
}) {
  const active = resource.status === "queued" || resource.status === "processing";
  return (
    <section className="seh-export-status" aria-labelledby={`${idPrefix}-export-title`}>
      <div className="seh-status-head"><div><h2 id={`${idPrefix}-export-title`}>Export status</h2><span className="seh-export-id">ID {resource.export_id.slice(0, 8)}</span></div><Badge tone={statusTone(resource.status)}>{resource.status}</Badge></div>
      <dl className="seh-export-facts">
        <div><dt>Format</dt><dd>{resource.format.toUpperCase()}</dd></div><div><dt>Mode</dt><dd>{resource.mode}</dd></div><div><dt>Stage</dt><dd>{resource.current_stage}</dd></div><div><dt>Documents</dt><dd>{resource.exported_document_count} / {resource.selected_document_count}</dd></div><div><dt>Rows</dt><dd>{resource.row_count}</dd></div>{resource.artifact_expires_at ? <div><dt>Expires</dt><dd>{formatDateTime(resource.artifact_expires_at)}</dd></div> : null}
      </dl>
      <div className="seh-progress"><label htmlFor={`${idPrefix}-export-progress`}>Progress: {resource.progress_percentage}%</label><progress id={`${idPrefix}-export-progress`} max={100} value={resource.progress_percentage} /></div>
      {stale ? <p className="seh-status-warning" role="status">Status updates are paused or retrying.</p> : null}
      {error ? <p className="seh-status-error" role="alert">{error}</p> : null}
      {resource.status === "failed" ? <p className="seh-status-error">{publicExportError(resource.error_code)}</p> : null}
      {resource.status === "expired" ? <p>This artifact has expired. Create a new export from current results.</p> : null}
      <div className="seh-status-actions">
        {resource.status === "completed" && resource.download_url ? <a className="ds-button" data-variant="primary" href={exportDownloadPath(resource.export_id)}>Download</a> : null}
        {(active || stale) ? <Button onClick={onRefresh}>Refresh status</Button> : null}
        {(resource.status === "failed" || resource.status === "expired") ? <Button onClick={onNewExport}>Create new export</Button> : null}
        <Button variant="subtle" onClick={onDismiss}>Dismiss</Button>
      </div>
    </section>
  );
}
