"use client";

import type { Route } from "next";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, RouteState, Skeleton, StatusBadge } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { useDocumentMonitor } from "@/features/documents-list-upload-monitor/use-document-monitor";
import type { JobStatus } from "@/features/documents-list-upload-monitor/types";
import type { UserRole } from "@/lib/auth/session-types";
import { ApiError, normalizeApiError } from "@/lib/api/errors";

import { readDocumentDetail } from "./api";
import { DocumentOverview } from "./document-overview";
import { SourceViewAction } from "./source-view-action";
import type { DocumentDetail } from "./types";
import styles from "./document-detail-chunk-inspector.module.css";

const ACTIVE_STATUSES = new Set(["queued", "partitioning", "chunking", "vectorizing", "extracting"]);

export function DocumentDetailView({ documentId, role }: { documentId: string; role: UserRole }) {
  const [detail, setDetail] = useState<DocumentDetail>();
  const [detailError, setDetailError] = useState<ApiError>();
  const [loadingDetail, setLoadingDetail] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [sourceBlocked, setSourceBlocked] = useState(false);
  const terminalRef = useRef<JobStatus | undefined>(undefined);
  const status = useDocumentMonitor(documentId);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      await Promise.resolve();
      if (controller.signal.aborted) return;
      setLoadingDetail(true);
      setDetailError(undefined);
      try {
        const envelope = await readDocumentDetail(documentId, controller.signal);
        setDetail(envelope.data);
        setSourceBlocked(false);
      } catch (cause) {
        const error = normalizeApiError(cause);
        if (error.code !== "REQUEST_ABORTED") setDetailError(error);
      } finally {
        if (!controller.signal.aborted) setLoadingDetail(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [documentId, refreshKey]);

  useEffect(() => {
    const next = status.snapshot?.job_status;
    const previous = terminalRef.current;
    terminalRef.current = next;
    if (previous && previous !== "completed" && previous !== "failed" && (next === "completed" || next === "failed")) {
      queueMicrotask(() => setRefreshKey((value) => value + 1));
    }
  }, [status.snapshot?.job_status]);

  function refreshSource() {
    if (loadingDetail) return;
    setSourceBlocked(true);
    setRefreshKey((value) => value + 1);
  }

  if (loadingDetail && !detail) {
    return (
      <div className={styles.pageStack} aria-label="Loading document">
        <Skeleton shape="text" width="48%" />
        <Skeleton shape="panel" height="14rem" />
        <Skeleton shape="panel" height="18rem" />
      </div>
    );
  }

  if (!detail) {
    const unavailable = detailError?.status === 404 || detailError?.status === 403;
    return (
      <RouteState
        kind={unavailable ? "not-found" : detailError?.code === "NETWORK_ERROR" ? "offline" : "error"}
        title={unavailable ? "Document unavailable" : "Document couldn’t be loaded"}
        message={unavailable ? "This document is unavailable or you do not have access." : "Try again. If the problem continues, share the request ID with support."}
        requestId={detailError?.requestId}
        actionLabel={unavailable ? "Back to documents" : "Try again"}
        href={unavailable ? "/documents" : undefined}
        onAction={unavailable ? undefined : () => setRefreshKey((value) => value + 1)}
      />
    );
  }

  const canMonitor = role !== "viewer" && ACTIVE_STATUSES.has(detail.status);
  const canInspect = role !== "viewer" && status.snapshot?.stages.chunking === "completed";
  const monitorHref = `/documents/upload?document=${encodeURIComponent(documentId)}` as Route;
  const chunksHref = `/documents/${documentId}/chunks` as Route;
  const reviewHref = `/documents/${documentId}/review` as Route;
  const canReview = role !== "viewer" && detail.invoice !== null && detail.review_revision !== null
    && (detail.status === "pending_review" || detail.status === "approved" || detail.status === "rejected");

  return (
    <div className={styles.pageStack}>
      <PageHeader
        title={detail.file_name}
        description={`${detail.doc_type.replaceAll("_", " ")} document`}
        actions={(
          <>
            <StatusBadge status={detail.status} />
            <Link className="ds-button" data-variant="subtle" href="/documents">Back to documents</Link>
            {canMonitor ? <Link className="ds-button" data-variant="secondary" href={monitorHref}>Monitor processing</Link> : null}
            {canInspect ? <Link className="ds-button" data-variant="secondary" href={chunksHref}>Inspect chunks</Link> : null}
            {canReview ? (
              <Link className="ds-button" data-variant="primary" href={reviewHref}>
                {detail.status === "pending_review" ? "Review document" : "Review & audit"}
              </Link>
            ) : null}
            <SourceViewAction source={detail.source_view} blocked={sourceBlocked} refreshing={loadingDetail} onRefresh={refreshSource} compact />
          </>
        )}
      />

      {loadingDetail ? <Alert title="Refreshing document" message="Showing the last validated details while the latest response loads." /> : null}
      {detailError ? (
        <Alert
          tone="error"
          title={sourceBlocked ? "Source link couldn’t be refreshed" : "Document refresh failed"}
          message={`The last validated details remain visible.${detailError.requestId ? ` Request ID: ${detailError.requestId}` : ""}`}
          action={<Button onClick={() => setRefreshKey((value) => value + 1)}>Try again</Button>}
        />
      ) : null}

      <DocumentOverview
        detail={detail}
        progress={status.snapshot}
        statusError={status.error}
        statusStale={status.stale}
        statusPaused={status.paused}
        onRefreshStatus={status.refresh}
      />
    </div>
  );
}
