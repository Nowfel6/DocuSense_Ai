"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Alert, RouteState, Skeleton } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { ApiError } from "@/lib/api/errors";

import { dashboardUrl, readActivity, readDashboard } from "./api";
import { CurrentWorkload } from "./current-workload";
import { DashboardVisualizations } from "./dashboard-visualizations";
import { formatUtc } from "./format";
import { PeriodOverview } from "./period-overview";
import { RecentActivity } from "./recent-activity";
import { ReportControls } from "./report-controls";
import type { ActivityEnvelope, ActivityEventType, DashboardActivityViewProps, DashboardEnvelope, DashboardQuery } from "./types";
import styles from "./dashboard-activity.module.css";

interface SafeError { message: string; requestId?: string; retryAt?: number; forbidden?: boolean; unauthorized?: boolean }

function safeError(error: unknown): SafeError {
  if (!(error instanceof ApiError)) return { message: "The service could not be reached. Try again." };
  const messages: Record<string, string> = {
    RATE_LIMIT_EXCEEDED: "Too many dashboard requests were made.",
    ANALYTICS_SOURCE_UNAVAILABLE: "Dashboard analytics are temporarily unavailable.",
    ANALYTICS_DATA_INTEGRITY_ERROR: "Dashboard data could not be verified safely.",
    VALIDATION_FAILED: "The report options were not accepted.",
    INVALID_API_RESPONSE: "The service returned data that could not be verified safely.",
  };
  const base = messages[error.code] ?? error.message;
  return { message: error.retryAfterSeconds ? `${base} Retry in ${error.retryAfterSeconds} seconds.` : base, requestId: error.requestId, retryAt: error.retryAfterSeconds ? Date.now() + error.retryAfterSeconds * 1_000 : undefined, forbidden: error.status === 403 || error.code === "FORBIDDEN", unauthorized: error.status === 401 || error.code === "UNAUTHORIZED" };
}

export function DashboardActivityView({ role, initialState }: DashboardActivityViewProps) {
  const router = useRouter();
  const [query, setQuery] = useState<DashboardQuery>(initialState.query);
  const [dashboard, setDashboard] = useState<DashboardEnvelope | null>(null);
  const [activity, setActivity] = useState<ActivityEnvelope | null>(null);
  const [dashboardError, setDashboardError] = useState<SafeError | null>(null);
  const [activityError, setActivityError] = useState<SafeError | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [activityLoading, setActivityLoading] = useState(true);
  const [filter, setFilter] = useState<"" | ActivityEventType>("");
  const [offline, setOffline] = useState(false);
  const [dashboardRevision, setDashboardRevision] = useState(0);
  const [activityRevision, setActivityRevision] = useState(0);
  const [accessDenied, setAccessDenied] = useState(false);
  const [retryClock, setRetryClock] = useState(() => Date.now());
  const dashboardAbort = useRef<AbortController | null>(null);
  const activityAbort = useRef<AbortController | null>(null);
  const dashboardIdentity = useRef(0);
  const activityIdentity = useRef(0);
  const activityRetry = useRef<{ query: DashboardQuery; page: number; filter: "" | ActivityEventType; snapshot?: string } | null>(null);

  const loadDashboard = useCallback(async (candidate: DashboardQuery) => {
    dashboardAbort.current?.abort();
    const controller = new AbortController(); dashboardAbort.current = controller;
    const identity = ++dashboardIdentity.current;
    setDashboardLoading(true); setDashboardError(null);
    try {
      const response = await readDashboard(candidate, controller.signal);
      if (identity === dashboardIdentity.current) setDashboard(response);
    } catch (error) {
      if (identity === dashboardIdentity.current && !controller.signal.aborted) { const safe = safeError(error); if (safe.forbidden) { setDashboard(null); setActivity(null); setAccessDenied(true); } else { if (safe.unauthorized) setDashboard(null); setDashboardError(safe); } }
    } finally {
      if (identity === dashboardIdentity.current) setDashboardLoading(false);
    }
  }, []);

  const loadActivity = useCallback(async (candidate: DashboardQuery, page: number, selected: "" | ActivityEventType, snapshot?: string) => {
    activityAbort.current?.abort();
    const controller = new AbortController(); activityAbort.current = controller;
    const identity = ++activityIdentity.current;
    activityRetry.current = { query: candidate, page, filter: selected, snapshot };
    setActivityLoading(true); setActivityError(null);
    try {
      const response = await readActivity(candidate, role, page, selected ? [selected] : [], snapshot, controller.signal);
      if (identity === activityIdentity.current) setActivity(response);
    } catch (error) {
      if (identity === activityIdentity.current && !controller.signal.aborted) { const safe = safeError(error); if (safe.forbidden) { setDashboard(null); setActivity(null); setAccessDenied(true); } else { if (safe.unauthorized) setActivity(null); setActivityError(safe); } }
    } finally {
      if (identity === activityIdentity.current) setActivityLoading(false);
    }
  }, [role]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadDashboard(query), 0);
    return () => window.clearTimeout(timer);
  }, [dashboardRevision, loadDashboard, query]);
  useEffect(() => {
    const timer = window.setTimeout(() => void loadActivity(query, 1, filter), 0);
    return () => window.clearTimeout(timer);
  }, [activityRevision, filter, loadActivity, query]);
  useEffect(() => {
    const update = () => setOffline(!navigator.onLine);
    update(); window.addEventListener("online", update); window.addEventListener("offline", update);
    return () => { window.removeEventListener("online", update); window.removeEventListener("offline", update); };
  }, []);
  useEffect(() => () => { dashboardAbort.current?.abort(); activityAbort.current?.abort(); }, []);
  const nextRetryAt = Math.max(dashboardError?.retryAt ?? 0, activityError?.retryAt ?? 0);
  useEffect(() => {
    if (nextRetryAt <= retryClock) return;
    const timer = window.setTimeout(() => setRetryClock(Date.now()), nextRetryAt - retryClock + 20);
    return () => window.clearTimeout(timer);
  }, [nextRetryAt, retryClock]);

  function apply(next: DashboardQuery) {
    setQuery(next);
    router.replace(dashboardUrl(next) as Route, { scroll: false });
  }

  function reset() {
    const next: DashboardQuery = { bucket: "day" };
    setQuery(next); router.replace("/dashboard", { scroll: false });
  }

  function refresh() {
    setDashboardRevision((value) => value + 1);
    setActivityRevision((value) => value + 1);
  }

  function page(next: number) {
    if (!activity || next < 1 || next > activity.pagination.total_pages || next === activity.pagination.page) return;
    void loadActivity(query, next, filter, activity.data.snapshot_at);
  }

  const bothInitialFailed = !dashboard && !activity && dashboardError && activityError;
  if (accessDenied) return <RouteState kind="forbidden" title="Dashboard access denied" message="Your current session cannot access dashboard analytics." actionLabel="Go to documents" href="/documents" />;
  return (
    <main className={styles.root}>
      <PageHeader title="Dashboard" description="Current workload, period performance, and recent workspace activity." actions={<Button variant="secondary" disabled={offline} isPending={dashboardLoading || activityLoading} pendingLabel="Refreshing…" onClick={refresh}><RefreshCw aria-hidden="true" size={17} />Refresh</Button>} />
      <p className="dba-eyebrow">Operations overview</p>
      {initialState.error ? <Alert tone="warning" title="Report URL reset" message={initialState.error} /> : null}
      {offline ? <Alert tone="warning" title="Offline — showing last loaded data" message="Reconnect, then refresh when you are ready. No automatic request will run." /> : null}
      {bothInitialFailed ? <Alert tone="error" title="Dashboard unavailable" message="Analytics and recent activity could not be loaded. Retry each section below." /> : null}
      <ReportControls key={dashboardUrl(query)} query={query} pending={dashboardLoading} onApply={apply} onReset={reset} />
      {dashboardError ? <Alert tone="error" title="Analytics unavailable" message={`${dashboardError.message}${dashboardError.requestId ? ` Request ID: ${dashboardError.requestId}` : ""}`} action={<Button disabled={offline || (dashboardError.retryAt ?? 0) > retryClock} onClick={() => void loadDashboard(query)}>Retry analytics</Button>} /> : null}
      {!dashboard && dashboardLoading ? <section aria-label="Loading dashboard analytics" className="dba-loading"><Skeleton shape="panel" height={150} /><Skeleton shape="panel" height={260} /></section> : null}
      {dashboard ? <div className="dba-dashboard-data" aria-busy={dashboardLoading || undefined}>
        {dashboardLoading ? <p className="dba-refresh-note" role="status">Refreshing analytics…</p> : null}
        <p className="dba-updated">Updated {formatUtc(dashboard.meta.timestamp)}</p>
        <CurrentWorkload metrics={dashboard.data.current} snapshot={dashboard.data.period.snapshot_at} />
        <PeriodOverview metrics={dashboard.data.period_metrics} period={dashboard.data.period} />
        <DashboardVisualizations data={dashboard.data} />
      </div> : null}
      <RecentActivity role={role} envelope={activity} loading={activityLoading} error={activityError} filter={filter} offline={offline} retryDisabled={(activityError?.retryAt ?? 0) > retryClock} onFilter={setFilter} onPage={page} onRetry={() => { const retry = activityRetry.current; if (retry) void loadActivity(retry.query, retry.page, retry.filter, retry.snapshot); else void loadActivity(query, 1, filter); }} />
      <section className="dba-quick-actions" aria-labelledby="dba-actions-title"><div><h2 id="dba-actions-title">Quick actions</h2><p>Continue to a focused workspace.</p></div><div><Link className="ds-button" data-variant="secondary" href="/documents">All documents</Link><Link className="ds-button" data-variant="secondary" href="/documents/search">Search &amp; export</Link>{role !== "viewer" ? <Link className="ds-button" data-variant="primary" href="/documents/upload">Upload documents</Link> : null}</div></section>
    </main>
  );
}
