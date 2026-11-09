"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, normalizeApiError } from "@/lib/api/errors";

import { readDocumentProgress } from "./api";
import type { DocumentProgress } from "./types";

const BACKOFF_SECONDS = [2, 4, 8, 16, 30] as const;

export function monitorRetryDelay(error: ApiError, failureCount: number): number | null {
  if (error.status === 429 && error.retryAfterSeconds) return error.retryAfterSeconds;
  if (error.code === "NETWORK_ERROR" || error.status === 429 || (error.status !== undefined && error.status >= 500)) {
    return BACKOFF_SECONDS[Math.min(failureCount, BACKOFF_SECONDS.length - 1)];
  }
  return null;
}

export function useDocumentMonitor(documentId: string) {
  const [snapshot, setSnapshot] = useState<DocumentProgress>();
  const [error, setError] = useState<ApiError>();
  const [loading, setLoading] = useState(true);
  const [stale, setStale] = useState(false);
  const [paused, setPaused] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const snapshotRef = useRef<DocumentProgress | undefined>(undefined);
  const refresh = useCallback(() => setRefreshKey((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    let inFlight = false;
    let failures = 0;
    let latest = snapshotRef.current;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;

    async function poll() {
      await Promise.resolve();
      if (!active || inFlight) return;
      if (document.hidden || !navigator.onLine) {
        setPaused(true);
        setLoading(false);
        return;
      }
      inFlight = true;
      setPaused(false);
      setLoading(true);
      controller = new AbortController();
      try {
        const envelope = await readDocumentProgress(documentId, controller.signal);
        if (!active) return;
        latest = envelope.data;
        snapshotRef.current = latest;
        setSnapshot(latest);
        setError(undefined);
        setStale(false);
        failures = 0;
        if (latest.job_status !== "completed" && latest.job_status !== "failed") {
          timer = setTimeout(() => void poll(), 2_000);
        }
      } catch (cause) {
        if (!active || controller.signal.aborted) return;
        const nextError = normalizeApiError(cause);
        setError(nextError);
        setStale(Boolean(latest));
        const delay = monitorRetryDelay(nextError, failures);
        if (delay !== null && nextError.status !== 401 && nextError.status !== 404 && nextError.code !== "INVALID_API_RESPONSE") {
          failures += 1;
          timer = setTimeout(() => void poll(), delay * 1_000);
        }
      } finally {
        inFlight = false;
        if (active) setLoading(false);
      }
    }

    function resume() {
      if (timer) clearTimeout(timer);
      if (!document.hidden && navigator.onLine) void poll();
      else setPaused(true);
    }
    void poll();
    document.addEventListener("visibilitychange", resume);
    window.addEventListener("online", resume);
    window.addEventListener("offline", resume);
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
      controller?.abort();
      document.removeEventListener("visibilitychange", resume);
      window.removeEventListener("online", resume);
      window.removeEventListener("offline", resume);
    };
  }, [documentId, refreshKey]);

  return { snapshot, error, loading, stale, paused, refresh };
}
