"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Badge, EmptyState, Skeleton } from "@/components/ui/feedback";
import { SelectField } from "@/components/ui/fields";
import { normalizeApiError, type ApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/formatting/format";

import { readAudit } from "./api";
import type { AuditAction, AuditEnvelope } from "./types";
import styles from "./human-review-studio.module.css";

const ACTION_LABELS: Record<AuditAction, string> = {
  field_edited: "Fields edited",
  approved: "Approved",
  rejected: "Rejected",
  reopened: "Reopened",
};

function safeValue(value: unknown) {
  if (value === undefined) return "Not recorded";
  const rendered = typeof value === "string" ? value : JSON.stringify(value);
  return rendered.length > 500 ? `${rendered.slice(0, 500)}…` : rendered;
}

export function AuditHistory({ documentId, refreshToken }: { documentId: string; refreshToken: number }) {
  const [page, setPage] = useState(1);
  const [action, setAction] = useState<AuditAction | "">("");
  const [result, setResult] = useState<AuditEnvelope>();
  const [error, setError] = useState<ApiError>();
  const [pending, setPending] = useState(true);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setPending(true);
      setError(undefined);
      try {
        setResult(await readAudit(documentId, page, action || undefined, controller.signal));
      } catch (cause) {
        const next = normalizeApiError(cause);
        if (next.code !== "REQUEST_ABORTED") setError(next);
      } finally {
        if (!controller.signal.aborted) setPending(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [action, documentId, page, refreshToken, retry]);

  return (
    <section className={styles.section} aria-labelledby="audit-heading">
      <div className={styles.sectionHeading}>
        <div><h2 id="audit-heading">Audit history</h2><p>Immutable review activity from the server.</p></div>
        <SelectField label="Filter action" value={action} onChange={(event) => { setAction(event.currentTarget.value as AuditAction | ""); setPage(1); }}>
          <option value="">All actions</option>
          {Object.entries(ACTION_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </SelectField>
      </div>
      {error ? <Alert tone="error" title="Audit history couldn’t be loaded" message={error.requestId ? `Request ID: ${error.requestId}` : "The last validated page remains visible."} action={<Button onClick={() => setRetry((value) => value + 1)}>Try again</Button>} /> : null}
      {pending && !result ? <><Skeleton shape="row" height="5rem" /><Skeleton shape="row" height="5rem" /></> : null}
      {pending && result ? <p className={styles.staleText}>Refreshing audit history…</p> : null}
      {!pending && result?.data.length === 0 ? <EmptyState title="No audit events" message="No review events match this filter." /> : null}
      <ol className={styles.auditList}>
        {result?.data.map((event) => (
          <li key={event.audit_event_id}>
            <div className={styles.auditHeading}>
              <div><strong>{ACTION_LABELS[event.action]}</strong><span>{event.actor_display_name ?? "Unknown reviewer"} · {formatDateTime(event.created_at)}</span></div>
              <Badge tone={event.action === "approved" ? "success" : event.action === "rejected" ? "danger" : "technical"}>Revision {event.review_revision}</Badge>
            </div>
            <p>{event.from_status.replaceAll("_", " ")} → {event.to_status.replaceAll("_", " ")}</p>
            {event.reason ? <p><strong>Reason:</strong> {event.reason}</p> : null}
            {event.note ? <p><strong>Note:</strong> {event.note}</p> : null}
            {event.changes.length ? (
              <details><summary>{event.changes.length} changed value{event.changes.length === 1 ? "" : "s"}</summary>
                <ul>{event.changes.map((change, index) => <li key={`${change.field_path}-${index}`}><code>{change.field_path}</code>: {safeValue(change.old_value)} → {safeValue(change.new_value)}</li>)}</ul>
              </details>
            ) : null}
            <small>Request ID: {event.request_id}</small>
          </li>
        ))}
      </ol>
      {result && result.pagination.total_pages > 1 ? (
        <div className={styles.pagination} aria-label="Audit pagination">
          <Button size="compact" variant="subtle" disabled={!result.pagination.has_prev || pending} onClick={() => setPage((value) => value - 1)}>Previous</Button>
          <span>Page {result.pagination.page} of {result.pagination.total_pages}</span>
          <Button size="compact" variant="subtle" disabled={!result.pagination.has_next || pending} onClick={() => setPage((value) => value + 1)}>Next</Button>
        </div>
      ) : null}
    </section>
  );
}
