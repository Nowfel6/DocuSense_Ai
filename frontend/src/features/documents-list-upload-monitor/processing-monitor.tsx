"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Skeleton, StatusBadge } from "@/components/ui/feedback";

import { ProcessingStageRail } from "./processing-stage-rail";
import type { UploadAccepted } from "./types";
import { useDocumentMonitor } from "./use-document-monitor";
import styles from "./documents-list-upload-monitor.module.css";

export function ProcessingMonitor({
  documentId,
  accepted,
  onUploadAnother,
}: {
  documentId: string;
  accepted?: UploadAccepted;
  onUploadAnother: () => void;
}) {
  const { snapshot, error, loading, stale, paused, refresh } = useDocumentMonitor(documentId);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => { if (accepted) headingRef.current?.focus(); }, [accepted]);

  if (loading && !snapshot) {
    return <section className={styles.monitorPanel} aria-label="Loading document processing status"><Skeleton shape="panel" height="18rem" /></section>;
  }

  const terminal = snapshot?.job_status === "completed" || snapshot?.job_status === "failed";
  const terminalTitle = snapshot?.job_status === "failed" ? "Processing failed"
    : snapshot?.job_status === "completed" && snapshot.status === "pending_review" ? "Processing complete — review required"
    : snapshot?.job_status === "completed" && snapshot.status === "approved" ? "Processing complete — approved"
    : snapshot?.job_status === "completed" ? "Processing complete" : undefined;
  const terminalMessage = snapshot?.job_status === "failed"
    ? snapshot.error?.message ?? "The document could not be processed."
    : snapshot?.status === "pending_review" ? "The document finished processing and is waiting for review."
    : snapshot?.status === "approved" ? "The backend marked this document approved."
    : terminal ? `Document status: ${snapshot?.status.replaceAll("_", " ")}.` : undefined;

  return (
    <section className={styles.monitorPanel} aria-labelledby="accepted-heading">
      <div className={styles.monitorHeading}>
        <div>
          <h2 ref={headingRef} id="accepted-heading" tabIndex={-1}>Document accepted</h2>
          <p title={accepted?.file_name}>{accepted?.file_name ?? `Document ${documentId.slice(0, 8)}…`}</p>
          <span className={styles.documentId}>Document ID: <span>{documentId}</span></span>
        </div>
        {snapshot ? (
          <dl className={styles.statusPairs}>
            <div><dt>Job status</dt><dd><Badge tone={snapshot.job_status === "failed" ? "danger" : snapshot.job_status === "completed" ? "success" : "technical"}>{snapshot.job_status.replaceAll("_", " ")}</Badge></dd></div>
            <div><dt>Document status</dt><dd><StatusBadge status={snapshot.status} /></dd></div>
          </dl>
        ) : null}
      </div>

      {snapshot ? (
        <>
          <div className={styles.persistedProgress}>
            <span>{snapshot.progress_percentage}% persisted processing progress</span>
            <progress max="100" value={snapshot.progress_percentage}>{snapshot.progress_percentage}%</progress>
          </div>
          <ProcessingStageRail stages={snapshot.stages} />
        </>
      ) : null}

      {accepted?.warnings.map((warning) => <Alert key={warning.code} tone="warning" title="Upload warning" message={warning.message} />)}
      {paused ? <Alert tone="warning" title={navigator.onLine ? "Status updates paused" : "You’re offline"} message="Status will refresh when this page is visible and online." /> : null}
      {stale ? <Alert tone="warning" title="Status may be out of date" message="The latest status could not be loaded. DocuSense will retry without overlapping requests." /> : null}
      {error && !stale ? (
        <Alert
          tone="error"
          title={error.status === 404 ? "Document status unavailable" : "Status couldn’t be loaded"}
          message={`The status is unavailable without revealing document ownership.${error.requestId ? ` Request ID: ${error.requestId}` : ""}`}
        />
      ) : null}
      {terminalTitle && terminalMessage ? <Alert tone={snapshot?.job_status === "failed" ? "error" : "success"} title={terminalTitle} message={terminalMessage} /> : null}

      <div className={styles.monitorActions}>
        {!terminal && error?.status !== 404 ? <Button onClick={refresh} disabled={loading}>Refresh status</Button> : null}
        <Link className="ds-button" data-variant="secondary" href="/documents">Back to documents</Link>
        <Button variant="subtle" onClick={onUploadAnother}>Upload another</Button>
      </div>
      <p className={styles.visuallyHidden} aria-live="polite">
        {terminalTitle ?? (snapshot ? `Processing stage ${snapshot.current_stage}.` : "")}
      </p>
    </section>
  );
}
