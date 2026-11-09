"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";

import { Button } from "@/components/ui/button";
import { SelectField } from "@/components/ui/fields";
import { Alert, EmptyState, Skeleton } from "@/components/ui/feedback";
import { Drawer, Dialog } from "@/components/ui/overlays";
import { PageHeader } from "@/components/ui/page-header";
import { ApiError } from "@/lib/api/errors";

import { createExport, readExport, searchDocuments, serializeSearch } from "./api";
import { ExportStatusPanel } from "./export-status-panel";
import { canonicalSearchParams } from "./search-query";
import { SearchComposer } from "./search-composer";
import { ResultSummary, SearchResults } from "./search-results";
import type { ExportFormat, ExportResource, FieldErrors, SearchDraft, SearchEnvelope, SearchHubProps } from "./types";
import styles from "./document-search-export.module.css";

interface PendingIntent { ids: string[]; format: ExportFormat; key: string }

function safeError(error: unknown): { message: string; requestId?: string; uncertain?: boolean } {
  if (error instanceof ApiError) return {
    message: error.message,
    requestId: error.requestId,
    uncertain: error.code === "NETWORK_ERROR" || error.code === "REQUEST_ABORTED",
  };
  return { message: "The request could not be completed safely." };
}

export function DocumentSearchExportHub({ role, initialState }: SearchHubProps) {
  const router = useRouter();
  const [draft, setDraft] = useState<SearchDraft>({ ...initialState.draft, document_statuses: [...initialState.draft.document_statuses] });
  const [committed, setCommitted] = useState<SearchDraft | null>(null);
  const [results, setResults] = useState<SearchEnvelope | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchRequestId, setSearchRequestId] = useState<string | undefined>();
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [format, setFormat] = useState<ExportFormat>("csv");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [exportDrawerOpen, setExportDrawerOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [pendingIntent, setPendingIntent] = useState<PendingIntent | null>(null);
  const [exportResource, setExportResource] = useState<ExportResource | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [pollStale, setPollStale] = useState(false);
  const [pollFailureCount, setPollFailureCount] = useState(0);
  const [pollRetryAfter, setPollRetryAfter] = useState<number | null>(null);
  const searchAbort = useRef<AbortController | null>(null);
  const searchIdentity = useRef(0);
  const pollAbort = useRef<AbortController | null>(null);
  const pollCount = useRef(0);
  const initialSearchStarted = useRef(false);
  const initialRecoveryStarted = useRef(false);
  const canExport = role === "admin" || role === "operator";

  const replaceUrl = useCallback((state: SearchDraft, exportId = exportResource?.export_id ?? null) => {
    const query = canonicalSearchParams(state, canExport ? exportId : null);
    router.replace(`/documents/search${query ? `?${query}` : ""}` as Route, { scroll: false });
  }, [canExport, exportResource?.export_id, router]);

  const runSearch = useCallback(async (candidate: SearchDraft) => {
    const normalized = { ...candidate, page: Math.max(1, candidate.page), document_statuses: role === "viewer" ? ["approved" as const] : candidate.document_statuses };
    const serialized = serializeSearch(normalized);
    setErrors(serialized.errors);
    if (!serialized.request) return;
    searchAbort.current?.abort();
    const controller = new AbortController();
    searchAbort.current = controller;
    const identity = ++searchIdentity.current;
    setSearching(true);
    setSearchError(null);
    setSearchRequestId(undefined);
    setSelected(new Set());
    setCommitted(normalized);
    replaceUrl(normalized);
    try {
      const response = await searchDocuments(serialized.request, controller.signal);
      if (identity === searchIdentity.current) setResults(response);
    } catch (error) {
      if (identity !== searchIdentity.current || controller.signal.aborted) return;
      const safe = safeError(error);
      setSearchError(safe.message);
      setSearchRequestId(safe.requestId);
    } finally {
      if (identity === searchIdentity.current) setSearching(false);
    }
  }, [replaceUrl, role]);

  const refreshExport = useCallback(async (exportId: string) => {
    if (!canExport) return;
    pollAbort.current?.abort();
    const controller = new AbortController();
    pollAbort.current = controller;
    try {
      const resource = await readExport(exportId, controller.signal);
      setExportResource(resource);
      setExportError(null);
      setPollStale(false);
      setPollFailureCount(0);
      setPollRetryAfter(null);
      pollCount.current += 1;
    } catch (error) {
      if (controller.signal.aborted) return;
      const safe = safeError(error);
      setExportError(safe.message);
      setPollStale(true);
      setPollFailureCount((count) => count + 1);
      setPollRetryAfter(error instanceof ApiError ? error.retryAfterSeconds ?? null : null);
    }
  }, [canExport]);

  useEffect(() => {
    if (initialSearchStarted.current || !initialState.hasStructuredCriteria) return;
    initialSearchStarted.current = true;
    void runSearch(initialState.draft);
  }, [initialState.draft, initialState.hasStructuredCriteria, runSearch]);

  useEffect(() => {
    if (initialRecoveryStarted.current || !initialState.exportId || !canExport) return;
    initialRecoveryStarted.current = true;
    void refreshExport(initialState.exportId);
  }, [canExport, initialState.exportId, refreshExport]);

  useEffect(() => {
    if (!exportResource || (exportResource.status !== "queued" && exportResource.status !== "processing") || document.visibilityState === "hidden") return;
    const count = pollCount.current;
    const failureDelay = [2_000, 5_000, 10_000, 30_000][Math.min(Math.max(pollFailureCount - 1, 0), 3)];
    const delay = pollRetryAfter ? pollRetryAfter * 1_000 : pollFailureCount ? failureDelay : count < 5 ? 2_000 : count < 12 ? 5_000 : 10_000;
    const timer = window.setTimeout(() => void refreshExport(exportResource.export_id), delay);
    return () => window.clearTimeout(timer);
  }, [exportResource, pollFailureCount, pollRetryAfter, refreshExport]);

  useEffect(() => {
    function visible() {
      if (document.visibilityState === "visible" && exportResource && (exportResource.status === "queued" || exportResource.status === "processing")) void refreshExport(exportResource.export_id);
    }
    document.addEventListener("visibilitychange", visible);
    return () => document.removeEventListener("visibilitychange", visible);
  }, [exportResource, refreshExport]);

  useEffect(() => () => { searchAbort.current?.abort(); pollAbort.current?.abort(); }, []);

  function updateDraft(patch: Partial<SearchDraft>) {
    setDraft((current) => ({ ...current, ...patch, page: patch.page ?? 1 }));
  }

  function page(nextPage: number) {
    if (!committed || nextPage < 1 || results && nextPage > Math.max(results.pagination.total_pages, 1)) return;
    const next = { ...committed, page: nextPage };
    setDraft(next);
    void runSearch(next);
  }

  function toggle(id: string, checked: boolean) {
    setSelected((current) => { const next = new Set(current); if (checked) next.add(id); else next.delete(id); return next; });
  }

  function togglePage(checked: boolean) {
    setSelected(checked && results ? new Set(results.data.filter((item) => item.export_eligible).map((item) => item.document_id)) : new Set());
  }

  async function submitExport(intent?: PendingIntent) {
    const nextIntent = intent ?? { ids: [...selected], format, key: crypto.randomUUID() };
    if (!nextIntent.ids.length) return;
    setPendingIntent(nextIntent);
    setCreating(true);
    setExportError(null);
    try {
      const accepted = await createExport(nextIntent.ids, nextIntent.format, nextIntent.key);
      setExportResource(accepted.resource);
      setPendingIntent(null);
      setSelected(new Set());
      pollCount.current = 0;
      setPollFailureCount(0);
      setPollRetryAfter(null);
      replaceUrl(committed ?? draft, accepted.resource.export_id);
      setExportDrawerOpen(true);
    } catch (error) {
      const safe = safeError(error);
      setExportError(safe.message);
      if (!safe.uncertain) setPendingIntent(null);
    } finally {
      setCreating(false);
      setConfirmOpen(false);
    }
  }

  function dismissExport() {
    pollAbort.current?.abort();
    setExportResource(null);
    setExportError(null);
    setPollStale(false);
    setPollFailureCount(0);
    setPollRetryAfter(null);
    setExportDrawerOpen(false);
    replaceUrl(committed ?? draft, null);
  }

  function reset() {
    searchAbort.current?.abort();
    const empty: SearchDraft = { query: "", document_statuses: [], document_type: "", supplier: "", currency: "", invoice_date_from: "", invoice_date_to: "", uploaded_from: "", uploaded_to: "", min_total: "", max_total: "", sort_by: "created_at", order: "desc", page: 1, page_size: 20 };
    pollAbort.current?.abort();
    setDraft(empty); setCommitted(null); setResults(null); setErrors({}); setSearchError(null); setSelected(new Set());
    setExportResource(null); setExportError(null); setPollStale(false); setPollFailureCount(0); setPollRetryAfter(null); setExportDrawerOpen(false);
    router.replace("/documents/search", { scroll: false });
    setResetOpen(false);
  }

  return (
    <main className={styles.root}>
      <PageHeader title="Search & export" description={role === "viewer" ? "Search approved documents in your organization." : "Find processed documents and create governed exports from eligible approved records."} />
      <SearchComposer draft={draft} errors={errors} viewer={role === "viewer"} pending={searching && !results} filtersOpen={filtersOpen} onFiltersOpen={setFiltersOpen} onChange={updateDraft} onSubmit={() => void runSearch({ ...draft, page: 1 })} onReset={() => exportResource ? setResetOpen(true) : reset()} />
      {searchError ? <Alert tone="error" title="Search unavailable" message={`${searchError}${searchRequestId ? ` Request ID: ${searchRequestId}` : ""}`} action={committed ? <Button onClick={() => void runSearch(committed)}>Retry</Button> : undefined} /> : null}
      {!results && searching ? <div className="seh-loading" aria-label="Loading search results"><Skeleton shape="panel" height={220} /></div> : null}
      {!results && !searching && !searchError ? <EmptyState title="Search your documents" message="Enter private search text or choose at least one structured filter." /> : null}
      {results ? <div className={exportResource ? "seh-workspace seh-with-export" : "seh-workspace"}><section className="seh-results" aria-label="Search results"><ResultSummary envelope={results} refreshing={searching} />{canExport ? <section className="seh-export-composer" aria-label="Create export"><span aria-live="polite">{selected.size} selected on this page</span><SelectField label="Export format" value={format} disabled={creating} onChange={(event) => setFormat(event.target.value as ExportFormat)}><option value="csv">CSV</option><option value="xlsx">XLSX</option><option value="json">JSON</option></SelectField><Button variant="subtle" disabled={!selected.size || creating} onClick={() => setSelected(new Set())}>Clear</Button><Button variant="primary" disabled={!selected.size} isPending={creating} onClick={() => setConfirmOpen(true)}>Create export</Button>{pendingIntent && exportError ? <Button onClick={() => void submitExport(pendingIntent)}>Retry exact request</Button> : null}{exportResource ? <Button className="seh-status-trigger" onClick={() => setExportDrawerOpen(true)}>Open export status</Button> : null}</section> : <Alert title="Approved-only search" message="Your viewer role can open approved documents but cannot create or download exports." />}
      <SearchResults envelope={results} semantic={Boolean(committed?.query.trim())} canExport={canExport} selected={selected} onToggle={toggle} onTogglePage={togglePage} onPage={page} /></section>{exportResource ? <aside className="seh-status-rail"><ExportStatusPanel resource={exportResource} stale={pollStale} error={exportError} onRefresh={() => void refreshExport(exportResource.export_id)} onDismiss={dismissExport} onNewExport={dismissExport} /></aside> : null}</div> : null}
      {exportError && !exportResource ? <Alert tone="error" title="Export not created" message={exportError} /> : null}
      <Dialog open={confirmOpen} title="Create export" description={`Create a ${format.toUpperCase()} export for ${selected.size} selected documents? The backend will verify eligibility again.`} confirmLabel="Create export" initialFocus="cancel" pending={creating} onConfirm={() => void submitExport()} onClose={() => setConfirmOpen(false)} />
      <Dialog open={resetOpen} title="Reset search and dismiss export status?" description="This clears local search and status state. It does not delete the backend export history." confirmLabel="Reset" initialFocus="cancel" onConfirm={reset} onClose={() => setResetOpen(false)} />
      {exportDrawerOpen && exportResource ? <Drawer open title="Export progress" placement="right" onClose={() => setExportDrawerOpen(false)}><ExportStatusPanel idPrefix="drawer" resource={exportResource} stale={pollStale} error={exportError} onRefresh={() => void refreshExport(exportResource.export_id)} onDismiss={dismissExport} onNewExport={dismissExport} /></Drawer> : null}
    </main>
  );
}
