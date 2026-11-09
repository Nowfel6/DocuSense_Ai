"use client";

import type { Route } from "next";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Badge, EmptyState, RouteState, Skeleton, StatusBadge } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";
import { useDocumentMonitor } from "@/features/documents-list-upload-monitor/use-document-monitor";
import { ApiError, normalizeApiError } from "@/lib/api/errors";

import { readDocumentDetail, readWorkbench } from "./api";
import { ItemInspector } from "./item-inspector";
import type {
  DocumentDetail,
  EvidenceResponse,
  SelectedWorkbenchItem,
  WorkbenchEnvelope,
  WorkbenchMode,
  WorkbenchQuery,
} from "./types";
import { normalizeWorkbenchQuery, queryForMode, queryWithPage, serializeWorkbenchQuery } from "./workbench-query";
import { WorkbenchFilterForm } from "./workbench-filter-form";
import { WorkbenchResults } from "./workbench-results";
import styles from "./document-detail-chunk-inspector.module.css";

function subscribeWide(onChange: () => void) {
  const media = window.matchMedia("(min-width: 1440px)");
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

function readWide() {
  return window.matchMedia("(min-width: 1440px)").matches;
}

function workbenchHref(documentId: string, search: string): Route {
  return `/documents/${documentId}/chunks${search ? `?${search}` : ""}` as Route;
}

function hasFilters(query: WorkbenchQuery) {
  return query.mode === "chunks"
    ? Boolean(query.chunkType || query.pageNumber || query.retrievalRole || query.section || query.order !== "asc")
    : Boolean(query.fieldPath || query.validationState || query.minConfidence !== undefined);
}

function collectionLength(envelope: WorkbenchEnvelope) {
  return Array.isArray(envelope.data) ? envelope.data.length : envelope.data.items.length;
}

export function ChunkEvidenceWorkbench({ documentId }: { documentId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const sourceQuery = searchParams.toString();
  const normalized = useMemo(() => normalizeWorkbenchQuery(sourceQuery), [sourceQuery]);
  const query = normalized.query;
  const [detail, setDetail] = useState<DocumentDetail>();
  const [detailError, setDetailError] = useState<ApiError>();
  const [detailLoading, setDetailLoading] = useState(true);
  const [detailRefresh, setDetailRefresh] = useState(0);
  const [sourceBlocked, setSourceBlocked] = useState(false);
  const [loaded, setLoaded] = useState<{ mode: WorkbenchMode; envelope: WorkbenchEnvelope }>();
  const [collectionError, setCollectionError] = useState<ApiError>();
  const [collectionLoading, setCollectionLoading] = useState(true);
  const [collectionRefresh, setCollectionRefresh] = useState(0);
  const [selected, setSelected] = useState<SelectedWorkbenchItem | null>(null);
  const selectedTriggerRef = useRef<HTMLElement | null>(null);
  const wide = useSyncExternalStore(subscribeWide, readWide, () => false);
  const status = useDocumentMonitor(documentId);

  useEffect(() => {
    if (normalized.canonical !== sourceQuery) router.replace(workbenchHref(documentId, normalized.canonical));
  }, [documentId, normalized.canonical, router, sourceQuery]);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      await Promise.resolve();
      if (controller.signal.aborted) return;
      setDetailLoading(true);
      setDetailError(undefined);
      try {
        const response = await readDocumentDetail(documentId, controller.signal);
        setDetail(response.data);
        setSourceBlocked(false);
      } catch (cause) {
        const error = normalizeApiError(cause);
        if (error.code !== "REQUEST_ABORTED") setDetailError(error);
      } finally {
        if (!controller.signal.aborted) setDetailLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [detailRefresh, documentId]);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      await Promise.resolve();
      if (controller.signal.aborted) return;
      setCollectionLoading(true);
      setCollectionError(undefined);
      try {
        const response = await readWorkbench(documentId, query, controller.signal);
        if (response.pagination.total_pages > 0 && query.page > response.pagination.total_pages) {
          router.replace(workbenchHref(documentId, serializeWorkbenchQuery(queryWithPage(query, response.pagination.total_pages))));
          return;
        }
        if (response.pagination.total_pages === 0 && query.page !== 1) {
          router.replace(workbenchHref(documentId, serializeWorkbenchQuery(queryWithPage(query, 1))));
          return;
        }
        setLoaded({ mode: query.mode, envelope: response });
      } catch (cause) {
        const error = normalizeApiError(cause);
        if (error.code !== "REQUEST_ABORTED") setCollectionError(error);
      } finally {
        if (!controller.signal.aborted) setCollectionLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [collectionRefresh, documentId, query, router]);

  const envelope = loaded?.mode === query.mode ? loaded.envelope : undefined;

  const visibleSelection = !selected || !envelope || selected.mode !== query.mode
    ? null
    : selected.mode === "chunks"
      ? Array.isArray(envelope.data) && envelope.data.some((item) => item.chunk_id === selected.item.chunk_id) ? selected : null
      : !Array.isArray(envelope.data) && envelope.data.items.some((item) => item.field_path === selected.item.field_path) ? selected : null;

  function navigate(next: WorkbenchQuery) {
    setSelected(null);
    router.push(workbenchHref(documentId, serializeWorkbenchQuery(next)));
  }

  function selectMode(id: string) {
    const mode: WorkbenchMode = id === "evidence" ? "evidence" : "chunks";
    navigate(queryForMode(mode, query.pageSize));
  }

  function refreshSource() {
    if (detailLoading) return;
    setSourceBlocked(true);
    setDetailRefresh((value) => value + 1);
  }

  if (detailLoading && !detail) {
    return <div className={styles.pageStack} aria-label="Loading chunk and evidence workbench"><Skeleton shape="text" width="52%" /><Skeleton shape="panel" height="26rem" /></div>;
  }

  if (!detail) {
    const unavailable = detailError?.status === 403 || detailError?.status === 404;
    return <RouteState kind={unavailable ? "not-found" : detailError?.code === "NETWORK_ERROR" ? "offline" : "error"} title={unavailable ? "Document unavailable" : "Workbench couldn’t be loaded"} message={unavailable ? "This document is unavailable or you do not have access." : "Try again. If the problem continues, share the request ID with support."} requestId={detailError?.requestId} actionLabel={unavailable ? "Back to documents" : "Try again"} href={unavailable ? "/documents" : undefined} onAction={unavailable ? undefined : () => setDetailRefresh((value) => value + 1)} />;
  }

  const selectedKey = visibleSelection?.mode === "chunks" ? visibleSelection.item.chunk_id : visibleSelection?.item.field_path ?? null;
  const evidenceEnvelope = envelope && !Array.isArray(envelope.data) ? envelope as EvidenceResponse : undefined;
  const currentPanel = (
    <div className={styles.workbenchPanel}>
      <WorkbenchFilterForm key={normalized.canonical || query.mode} query={query} onApply={navigate} onClear={() => navigate(queryForMode(query.mode, query.pageSize))} />
      {collectionLoading && envelope ? <Alert title="Refreshing results" message="Showing the previous validated page while the latest response loads." /> : null}
      {collectionError ? (
        <Alert
          tone={collectionError.status === 409 ? "warning" : "error"}
          title={collectionError.status === 409 ? (query.mode === "chunks" ? "Chunks are not ready" : "Extraction evidence is not ready") : "Results couldn’t be loaded"}
          message={`${collectionError.status === 409 ? "Document processing has not completed the required stage." : "The request could not be completed safely."}${collectionError.requestId ? ` Request ID: ${collectionError.requestId}` : ""}`}
          action={<Button onClick={() => setCollectionRefresh((value) => value + 1)}>Try again</Button>}
        />
      ) : null}
      {collectionLoading && !envelope ? <Skeleton shape="panel" height="22rem" /> : null}
      {!collectionLoading && envelope && collectionLength(envelope) === 0 ? (
        <EmptyState
          title={hasFilters(query) ? "No results match these filters" : query.mode === "chunks" ? "No persisted chunks" : "No extraction evidence for this run"}
          message={hasFilters(query) ? "Change or clear the current filters." : query.mode === "chunks" ? "No chunks are available at the current processing checkpoint." : "Completed-run evidence is not available for this document."}
          action={hasFilters(query) ? <Button onClick={() => navigate(queryForMode(query.mode, query.pageSize))}>Clear filters</Button> : undefined}
        />
      ) : null}
      {envelope && collectionLength(envelope) > 0 ? (
        <WorkbenchResults
          query={query}
          envelope={envelope}
          selectedKey={selectedKey}
          onSelect={(next, trigger) => { selectedTriggerRef.current = trigger; setSelected(next); }}
          onPage={(page) => navigate(queryWithPage(query, page))}
        />
      ) : null}
    </div>
  );

  return (
    <div className={styles.workbenchPage}>
      <PageHeader
        title="Chunk and evidence workbench"
        description={`${detail.file_name} · persisted technical document data`}
        actions={<><StatusBadge status={detail.status} /><Link className="ds-button" data-variant="subtle" href={`/documents/${documentId}` as Route}>Back to document</Link></>}
      />
      {normalized.reset ? <Alert tone="warning" title="Some workbench filters were reset" message="Unsupported, repeated, or mode-incompatible values were removed." /> : null}
      {detailLoading ? <Alert title="Refreshing document context" message="The previous validated context remains visible." /> : null}
      {detailError ? <Alert tone="error" title={sourceBlocked ? "Source link couldn’t be refreshed" : "Document context refresh failed"} message={`The previous context remains visible.${detailError.requestId ? ` Request ID: ${detailError.requestId}` : ""}`} /> : null}
      <section className={styles.compactStatus} aria-labelledby="workbench-status-title">
        <div><h2 id="workbench-status-title">Current processing state</h2><p>Persisted snapshot; no processing history is inferred.</p></div>
        {status.snapshot ? <div className={styles.inspectorBadges}><Badge tone={status.snapshot.job_status === "failed" ? "danger" : status.snapshot.job_status === "completed" ? "success" : "technical"}>{status.snapshot.job_status}</Badge><Badge>{status.snapshot.current_stage}</Badge><span>{status.snapshot.progress_percentage}%</span></div> : <span>Not available</span>}
      </section>
      {status.stale ? <Alert tone="warning" title="Processing status may be out of date" message="The last validated status remains visible." /> : null}

      <div className={styles.workbenchGrid} data-wide={wide || undefined}>
        <main className={styles.workbenchMain}>
          <Tabs
            label="Workbench mode"
            selectedId={query.mode}
            onSelect={selectMode}
            items={[
              { id: "chunks", label: "Chunks", panel: query.mode === "chunks" ? currentPanel : null },
              { id: "evidence", label: "Extraction evidence", panel: query.mode === "evidence" ? currentPanel : null },
            ]}
          />
        </main>
        <ItemInspector
          selected={visibleSelection}
          evidence={evidenceEnvelope}
          source={detail.source_view}
          wide={wide}
          sourceBlocked={sourceBlocked}
          sourceRefreshing={detailLoading}
          onRefreshSource={refreshSource}
          onClose={() => setSelected(null)}
          returnFocusRef={selectedTriggerRef}
        />
      </div>
      <p className={styles.visuallyHidden} aria-live="polite">{visibleSelection ? "Evidence inspector opened." : ""}</p>
    </div>
  );
}
