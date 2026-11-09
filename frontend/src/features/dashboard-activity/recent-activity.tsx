"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";

import { Button } from "@/components/ui/button";
import { Alert, EmptyState, Skeleton } from "@/components/ui/feedback";
import { SelectField } from "@/components/ui/fields";
import { Pagination, TableFrame } from "@/components/ui/table";

import { formatUtc, statusLabel } from "./format";
import { safeActivityLink } from "./safe-activity-link";
import type { ActivityEnvelope, ActivityEventType, ActivityItem, DashboardRole } from "./types";

const summaries: Record<ActivityItem["summary_code"], string> = {
  "document.uploaded": "Document uploaded", "processing.completed": "Processing completed", "processing.failed": "Processing failed",
  "review.field_edited": "Review changes saved", "review.approved": "Document approved", "review.rejected": "Document rejected", "review.reopened": "Document reopened",
  "export.requested": "Export requested", "export.completed": "Export completed", "export.failed": "Export failed", "export.expired": "Export expired",
};

const filters: { value: "" | ActivityEventType; label: string }[] = [
  { value: "", label: "All activity" }, { value: "document_uploaded", label: "Document uploaded" },
  { value: "processing_completed", label: "Processing completed" }, { value: "processing_failed", label: "Processing failed" },
  { value: "review_saved", label: "Review saved" }, { value: "document_approved", label: "Document approved" },
  { value: "document_rejected", label: "Document rejected" }, { value: "document_reopened", label: "Document reopened" },
  { value: "export_requested", label: "Export requested" }, { value: "export_completed", label: "Export completed" },
  { value: "export_failed", label: "Export failed" }, { value: "export_expired", label: "Export expired" },
];

function useNarrow() {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 767px)");
    const update = () => setNarrow(query.matches);
    update(); query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return narrow;
}

function ActivityAction({ item, role }: { item: ActivityItem; role: DashboardRole }) {
  const href = safeActivityLink(item, role);
  return href ? <Link className="dba-inline-link" href={href as Route}>Open document</Link> : <span className="dba-muted">No action</span>;
}

export function RecentActivity({ role, envelope, loading, error, filter, offline, retryDisabled = false, onFilter, onPage, onRetry }: {
  role: DashboardRole;
  envelope: ActivityEnvelope | null;
  loading: boolean;
  error: { message: string; requestId?: string } | null;
  filter: "" | ActivityEventType;
  offline: boolean;
  retryDisabled?: boolean;
  onFilter: (filter: "" | ActivityEventType) => void;
  onPage: (page: number) => void;
  onRetry: () => void;
}) {
  const narrow = useNarrow();
  const items = envelope?.data.items ?? [];
  return (
    <section aria-labelledby="dba-activity-title" className="dba-activity">
      <div className="dba-section-heading"><div><h2 id="dba-activity-title">Recent activity</h2><p>Role-filtered events use an independent pagination snapshot.</p></div><SelectField label="Event type" value={filter} disabled={loading} onChange={(event) => onFilter(event.target.value as "" | ActivityEventType)}>{filters.map((item) => <option value={item.value} key={item.value || "all"}>{item.label}</option>)}</SelectField></div>
      {error ? <Alert tone="error" title="Activity unavailable" message={`${error.message}${error.requestId ? ` Request ID: ${error.requestId}` : ""}`} action={<Button disabled={offline || retryDisabled} onClick={onRetry}>Retry</Button>} /> : null}
      {!envelope && loading ? <div className="dba-activity-loading" aria-label="Loading recent activity"><Skeleton shape="panel" height={180} /></div> : null}
      {envelope && !items.length ? <EmptyState title="No matching activity" message="No activity matches this period and filter." action={filter ? <Button onClick={() => onFilter("")}>Reset filter</Button> : undefined} /> : null}
      {envelope && items.length && narrow ? <ul className="dba-activity-cards" aria-label="Recent activity">
        {items.map((item) => <li key={item.event_id}><strong>{summaries[item.summary_code]}</strong><span>{item.display_label}</span><dl><div><dt>Subject</dt><dd>{statusLabel(item.subject_type)}</dd></div><div><dt>Occurred</dt><dd>{formatUtc(item.occurred_at)}</dd></div><div><dt>Actor</dt><dd>{item.actor_display_name ?? "System"}</dd></div></dl><ActivityAction item={item} role={role} /></li>)}
      </ul> : null}
      {envelope && items.length && !narrow ? <TableFrame caption="Recent activity" headers={["Event", "Subject", "Occurred", "Actor", "Action"]}>
        {items.map((item) => <tr key={item.event_id}><td><strong>{summaries[item.summary_code]}</strong><span className="dba-cell-note">{item.display_label}</span></td><td>{statusLabel(item.subject_type)}</td><td>{formatUtc(item.occurred_at)}</td><td>{item.actor_display_name ?? "System"}</td><td><ActivityAction item={item} role={role} /></td></tr>)}
      </TableFrame> : null}
      {envelope && envelope.pagination.total_pages > 0 ? <div aria-busy={loading || undefined}><Pagination page={envelope.pagination.page} totalPages={envelope.pagination.total_pages} onFirst={() => onPage(1)} onPrevious={() => onPage(envelope.pagination.page - 1)} onNext={() => onPage(envelope.pagination.page + 1)} onLast={() => onPage(envelope.pagination.total_pages)} /></div> : null}
      {envelope && loading ? <p className="dba-refresh-note" role="status">Refreshing activity…</p> : null}
    </section>
  );
}
